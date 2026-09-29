"""Granica 1: surowe transakcje → agregaty (spec, Testing Decisions)."""

import itertools
from dataclasses import replace
from decimal import Decimal

import pandas as pd
import pytest
from pyspark.sql import types as T

from pipeline.aggregate import Reference, build_aggregates, load_reference

SCHEMA = T.StructType([
    T.StructField("tran_id_raw", T.LongType()),
    T.StructField("tran_id_gmt_tm", T.StringType()),
    T.StructField("pymt_crd_acct_num_raw", T.StringType()),
    T.StructField("transaction_type", T.StringType()),
    T.StructField("transaction_pos_entry_mode", T.StringType()),
    T.StructField("mrch_ctry_nm", T.StringType()),
    T.StructField("mrch_nm_raw", T.StringType()),
    T.StructField("mrch_catg_cd", T.ShortType()),
    T.StructField("mrch_city_nm_raw", T.StringType()),
    T.StructField("mrch_postal_code", T.StringType()),
    T.StructField("cs_tran_amt", T.DecimalType(38, 10)),
    T.StructField("channel_flg", T.StringType()),
    T.StructField("cp_flag", T.ShortType()),
    T.StructField("prch_dt", T.StringType()),
    T.StructField("lau_enr", T.StringType()),
    T.StructField("pstl_cd_enr", T.StringType()),
])

SUMMER = "2025-07-08"  # wtorek, CEST (+2)
WINTER = "2026-01-13"  # wtorek, CET (+1)
AUTUMN = "2025-10-14"  # wtorek, cennik III
ZONE = "90-001"

_ids = itertools.count(1)


def tx(card, gmt, day=SUMMER, mcc=5812, name="BISTRO", kod=ZONE, amount="10", cp=1,
       channel="cp_contactless", mode="Tap to pay", ttype="POS", home="95-100", lau="ZGIERZ",
       country="POLAND", city="LODZ"):
    return (next(_ids), gmt, card, ttype, mode, country, name, mcc, city, kod,
            Decimal(amount), channel, cp, day, lau, home)


@pytest.fixture(scope="session")
def ref(spark):
    groups = spark.createDataFrame(
        [(5812, "gastronomia", 75), (5411, "spozywcze_male", 20), (5462, "szybkie_uslugi", 15),
         (4111, "szybkie_uslugi", 15)],
        "mcc int, grupa string, czas_domyslny_min int",
    )
    tariff = spark.read.csv("data/cennik_spp.csv", header=True, inferSchema=True)
    meters = spark.createDataFrame([("438B", "A", ZONE)], "numer string, podstrefa string, kod_pocztowy string")
    return Reference(mcc_groups=groups, tariff=tariff, exclusions=["GLOVO", "WOLT"], meters=meters)


def run(spark, ref, rows, min_cards=1):
    out = build_aggregates(spark.createDataFrame(rows, SCHEMA), ref, min_cards=min_cards)
    return {k: [r.asDict() for r in v.collect()] for k, v in out.items()}


def parking(card, gmt, day=SUMMER, amount="4.60", cp=0, meter="438B", lau="ZGIERZ"):
    return tx(card, gmt, day=day, mcc=7523, name=f"SPP Lodz {meter}", kod="93-180", amount=amount, cp=cp,
              channel="mobile", lau=lau)


def test_online_delivery_and_transit_are_ignored_but_cp0_parking_counts(spark, ref):
    rows = [
        tx("c1", "083000", channel="eci", cp=0, mode="COF"),
        tx("c2", "083000", name="GLOVO LODZ"),
        tx("c3", "083000", mcc=4111, name="MPK-LODZ AUTOMAT 2192"),
        parking("c4", "080000", cp=0),
        tx("c4", "083000"),
    ]
    out = run(spark, ref, rows)
    [g] = out["agg_grupy"]
    assert g["karty_przyjezdne"] == 1
    assert g["wspolczynnik_kierowcow"] == 1.0


@pytest.mark.parametrize("day,gmt,block", [
    (SUMMER, "083000", "10-13"),  # 10:30 CEST
    (WINTER, "093000", "10-13"),  # 10:30 CET
    (WINTER, "083000", "07-10"),  # 09:30 CET
])
def test_gmt_is_converted_to_warsaw_time_with_dst(spark, ref, day, gmt, block):
    [g] = run(spark, ref, [tx("c1", gmt, day=day)])["agg_grupy"]
    assert g["blok"] == block


@pytest.mark.parametrize("gap_gmt,expected_minutes", [("093000", 60 + 75), ("103000", 75)])
def test_transactions_within_90_min_form_one_visit(spark, ref, gap_gmt, expected_minutes):
    rows = [tx("c1", "083000"), tx("c1", gap_gmt)]
    [g] = [r for r in run(spark, ref, rows)["agg_grupy"] if r["blok"] == "10-13"]
    assert g["mediana_czasu_wizyty_min"] == expected_minutes


def test_purchase_four_hours_after_payment_is_not_its_visit_target(spark, ref):
    rows = [parking("c1", "080000", meter="438B"), tx("c1", "120000", mcc=5462, name="PIEKARNIA")]
    [g] = run(spark, ref, rows)["agg_grupy"]
    assert g["blok"] == "13-16"  # start = zakup o 14:00, nie opłata o 10:00
    assert g["mediana_czasu_wizyty_min"] == 15
    assert g["wspolczynnik_kierowcow"] == 1.0


def test_purchase_after_payment_starts_visit_at_payment(spark, ref):
    rows = [parking("c1", "080000", meter="438B"), tx("c1", "090000", mcc=5462, name="PIEKARNIA")]
    [g] = run(spark, ref, rows)["agg_grupy"]
    assert g["blok"] == "10-13"
    assert g["mediana_czasu_wizyty_min"] == 60 + 15


def test_one_hour_amount_in_zone_a_without_discount_is_60_minutes(spark, ref):
    amount = str(Decimal("6.90") * Decimal("0.92"))
    out = run(spark, ref, [parking("c1", "080000", day=AUTUMN, amount=amount)])
    [p] = out["agg_parkomaty"]
    assert p["mediana_minut"] == 60.0
    assert p["podstrefa_zrodlo"] == "lokalizacja"


def test_group_with_29_cards_is_not_exported(spark, ref):
    rows = [tx(f"a{i}", "083000", mcc=5812) for i in range(29)]
    rows += [tx(f"b{i}", "083000", mcc=5411, name="SKLEP") for i in range(30)]
    out = run(spark, ref, rows, min_cards=30)
    assert {g["grupa"] for g in out["agg_grupy"]} == {"spozywcze_male"}


def test_zone_below_threshold_is_flagged_without_numbers(spark, ref):
    out = run(spark, ref, [tx(f"a{i}", "083000") for i in range(29)], min_cards=30)
    [z] = out["agg_strefy"]
    assert z["za_malo_danych"] and z["presja"] is None and z["karty_przyjezdne"] is None


def test_local_customers_are_not_visitors(spark, ref):
    out = run(spark, ref, [tx("c1", "083000", home=ZONE)])
    assert out["agg_grupy"] == []


def test_output_has_no_card_identifier(spark, ref):
    rows = [parking("c1", "080000"), tx("c1", "083000")]
    out = build_aggregates(spark.createDataFrame(rows, SCHEMA), ref, min_cards=1)
    for df in out.values():
        assert not {"card", "pymt_crd_acct_num_raw", "tran_id_raw"} & set(df.columns)
        assert not any(isinstance(f.dataType, T.ArrayType) for f in df.schema.fields)


def test_hub_postal_code_is_excluded_from_zones(spark, ref):
    rows = [tx(f"h{i}", "083000", kod="91-111", name=f"LIDL {i}") for i in range(5)]
    rows += [tx("c1", "083000")]
    out = {
        k: [r.asDict() for r in v.collect()]
        for k, v in build_aggregates(spark.createDataFrame(rows, SCHEMA), ref, min_cards=1,
                                     hub_min_merchants=3).items()
    }
    assert {z["kod"] for z in out["agg_strefy"]} == {ZONE}
    assert [h["kod"] for h in out["kody_zbiorcze"]] == ["91-111"]


def test_vending_and_online_names_are_excluded(spark, ref):
    ref2 = Reference(ref.mcc_groups, ref.tariff, ["AUTOMAT(?!YK)", r"\.(PL|COM|EU)\b"], ref.meters)
    rows = [tx("c1", "083000", name="KOFEINA AUTOMATY 1"), tx("c2", "083000", name="SKLEP.PL")]
    out = build_aggregates(spark.createDataFrame(rows, SCHEMA), ref2, min_cards=1)
    assert out["agg_grupy"].count() == 0


def test_mall_postal_code_is_excluded_from_zones(spark, ref):
    ref2 = Reference(ref.mcc_groups, ref.tariff, ref.exclusions, ref.meters, excluded_codes=["91-071"])
    rows = [tx("c1", "083000", kod="91-071", name="NEW YORKER"), tx("c2", "083000")]
    out = build_aggregates(spark.createDataFrame(rows, SCHEMA), ref2, min_cards=1)
    assert {r.kod for r in out["agg_strefy"].collect()} == {ZONE}


@pytest.mark.parametrize("kwargs", [
    {"ttype": "OTHER"},
    {"cp": 0},
    {"channel": "eci"},
    {"mode": "COF"},
    {"mode": "Manual key entry"},
    {"mcc": 4784, "name": "MINISTERSTWO FINANSO 01"},
], ids=["nie_POS_ATM", "cp_flag_0", "eci", "COF", "reczne", "mcc_4784"])
def test_each_filter_alone_drops_the_transaction(spark, ref, kwargs):
    # 4784 w mapowaniu grup, żeby sprawdzić filtr, a nie brak grupy.
    groups = ref.mcc_groups.unionByName(
        spark.createDataFrame([(4784, "szybkie_uslugi", 15)], "mcc int, grupa string, czas_domyslny_min int"))
    ref2 = Reference(groups, ref.tariff, ref.exclusions, ref.meters)
    base = {"mcc": 5812, "name": "BISTRO"}
    assert len(run(spark, ref2, [tx("c1", "083000", **{**base, **kwargs})])["agg_grupy"]) == 0
    assert len(run(spark, ref2, [tx("c1", "083000", **base)])["agg_grupy"]) == 1


def test_missing_gmt_time_000000_is_dropped_before_everything(spark, ref):
    # Bez filtra 5 sprzedawców pod jednym kodem zrobiłoby z niego kod zbiorczy.
    rows = [tx(f"h{i}", "000000", kod="91-111", name=f"SKLEP {i}") for i in range(5)]
    out = {k: [r.asDict() for r in v.collect()] for k, v in build_aggregates(
        spark.createDataFrame(rows, SCHEMA), ref, min_cards=1, hub_min_merchants=3).items()}
    assert out["kody_zbiorcze"] == [] and out["agg_grupy"] == [] and out["agg_strefy"] == []


@pytest.mark.parametrize("day,kept", [("2025-06-19", False), ("2025-06-18", True)])
def test_corpus_christi_2025_is_dropped(spark, ref, day, kept):
    assert len(run(spark, ref, [tx("c1", "083000", day=day)])["agg_grupy"]) == int(kept)


@pytest.mark.parametrize("day,season", [
    ("2025-05-27", None),  # przed reformą: tylko naturalny eksperyment
    ("2025-06-03", "lato"),
    ("2025-09-30", "lato"),
    ("2025-10-01", "rok_akademicki"),
    ("2026-06-30", "rok_akademicki"),
    ("2026-07-07", None),
])
def test_seasons_summer_vi_ix_and_academic_year_x_vi(spark, ref, day, season):
    out = run(spark, ref, [tx("c1", "083000", day=day)])["agg_grupy"]
    assert [g["sezon"] for g in out] == ([season] if season else [])


def test_missing_home_postal_code_counts_as_visitor(spark, ref):
    [g] = run(spark, ref, [tx("c1", "083000", home=None)])["agg_grupy"]
    assert g["karty_przyjezdne"] == 1


@pytest.mark.parametrize("visit_days,expected", [
    (["2025-07-08", "2025-07-15"], 1.75),  # tygodnie: [1.75, 1.75, 0] → mediana 1.75
    (["2025-07-08"], 0.0),                 # tygodnie: [1.75, 0, 0] → mediana 0
])
def test_pressure_is_median_over_weeks_with_empty_weeks_as_zero(spark, ref, visit_days, expected):
    rows = []
    for d in visit_days:
        rows += [parking("c1", "080000", day=d), tx("c1", "083000", day=d)]
    rows += [tx("c2", "083000", day="2025-07-22", kod="90-002")]  # trzeci tydzień sezonu w danych
    [g] = [r for r in run(spark, ref, rows)["agg_grupy"] if r["kod"] == ZONE]
    # 1 karta × kierowcy 1.0 × (opłata 10:00 → zakup 10:30 + 75 min) / 60
    assert g["mediana_czasu_wizyty_min"] == 105
    assert g["presja"] == pytest.approx(expected)


def test_mcc_groups_reference_maps_each_mcc_once_with_default_time(spark):
    ref = load_reference(spark, "data")
    rows = ref.mcc_groups.collect()
    assert len({r.mcc for r in rows}) == len(rows)
    assert all(r.grupa and r.czas_domyslny_min > 0 for r in rows)
    assert not {7523, 4784, 4111} & {r.mcc for r in rows}


def test_calibration_uses_only_multi_transaction_visits(spark, ref):
    rows = [
        tx("c1", "083000"), tx("c1", "090000"),                    # 30 min zmierzone
        tx("c2", "083000"), tx("c2", "093000"), tx("c2", "094000"),  # 70 min zmierzone
        tx("c3", "083000"), tx("c3", "093000"),                    # 60 min zmierzone
        tx("c4", "083000"),                                        # jedna transakcja: poza kalibracją
        tx("c5", "083000"), tx("c5", "110000"),                    # przerwa 150 min → dwie wizyty
    ]
    [k] = run(spark, ref, rows)["agg_kalibracja_czasow"]
    assert k["grupa"] == "gastronomia" and k["czas_domyslny_min"] == 75
    assert k["wizyty_wielotransakcyjne"] == 3 and k["karty"] == 3
    assert k["udzial_wielotransakcyjnych"] == pytest.approx(3 / 6)
    assert k["mediana_czasu_zmierzonego_min"] == 60


def test_calibration_measures_from_first_transaction_not_payment(spark, ref):
    rows = [parking("c1", "080000"), tx("c1", "083000"), tx("c1", "090000")]
    [k] = run(spark, ref, rows)["agg_kalibracja_czasow"]
    assert k["mediana_czasu_zmierzonego_min"] == 30


def test_calibration_group_with_29_cards_is_not_exported(spark, ref):
    rows = [r for i in range(29) for r in (tx(f"a{i}", "083000"), tx(f"a{i}", "090000"))]
    rows += [r for i in range(30) for r in (tx(f"b{i}", "083000", mcc=5411, name="SKLEP"),
                                            tx(f"b{i}", "084000", mcc=5411, name="SKLEP"))]
    out = run(spark, ref, rows, min_cards=30)
    assert [k["grupa"] for k in out["agg_kalibracja_czasow"]] == ["spozywcze_male"]


# ---------- cennik SPP i zmierzony popyt (ticket 07) ----------

PRE_REFORM = "2025-05-27"  # wtorek, cennik I (podstrefy z mapy 2024)


@pytest.fixture(scope="session")
def ref_meters(spark, ref):
    """Parkomaty z obecną podstrefą i podstrefą z mapy 2024: Fabryczna (dawne C → B), Bałucki Rynek (D → C)."""
    meters = spark.createDataFrame(
        [("1A", "A", "A", ZONE), ("438B", "A", "B", ZONE), ("440C", "B", "C", ZONE), ("300D", "C", "D", ZONE)],
        "numer string, podstrefa string, podstrefa_2024 string, kod_pocztowy string",
    )
    return replace(ref, meters=meters)


def paid(spark, ref, meter, day, pln, lau="ZGIERZ"):
    amount = str(Decimal(pln) * Decimal("0.92"))
    [p] = run(spark, ref, [parking("c1", "080000", day=day, amount=amount, meter=meter, lau=lau)])["agg_parkomaty"]
    return p


@pytest.mark.parametrize("meter,day,pln,lau,expected", [
    ("1A", AUTUMN, "6.00", "LODZ", 60.0),                      # A z ulgą mieszkańca: 1. h = 6,00
    ("1A", AUTUMN, "6.00", "ZGIERZ", round(60 * 6 / 6.9, 1)),  # A bez ulgi: 1. h = 6,90
    ("1A", AUTUMN, "15.10", "ZGIERZ", 120.0),                  # 6,90 + 8,20 = 2 h
    ("1A", AUTUMN, "24.90", "ZGIERZ", 180.0),                  # + 9,80 = 3 h (przykład z lodz-spp.md)
    ("1A", AUTUMN, "28.35", "ZGIERZ", 210.0),                  # + 3,45 = pół 4. godziny po 6,90
    ("1A", AUTUMN, "2.00", "ZGIERZ", 30.0),                    # poniżej stawki za 30 min → minimalny bilet
    ("300D", AUTUMN, "6.00", "ZGIERZ", 60.0),                  # C bez ulgi: 1. h = 6,00
    ("300D", AUTUMN, "5.00", "LODZ", 60.0),                    # C z ulgą: 1. h = 5,00
    ("1A", SUMMER, "6.00", "ZGIERZ", 60.0),                    # okres II: wszyscy płacą stawki „z ulgą”
    ("438B", "2025-06-02", "6.00", "ZGIERZ", 60.0),            # okres II od poniedziałku 2.06.2025
    ("1A", PRE_REFORM, "5.00", "ZGIERZ", 60.0),                # okres I: A = 5,00 za 1. h
    ("438B", PRE_REFORM, "4.00", "ZGIERZ", 60.0),              # okres I: 438B był w B (mapa 2024), dziś w A
    ("440C", PRE_REFORM, "5.00", "ZGIERZ", 60.0),              # dawne C (Fabryczna) płaciło stawki A
    ("440C", AUTUMN, "6.00", "ZGIERZ", 60.0),                  # ... a od reformy jest w B
    ("300D", PRE_REFORM, "4.00", "ZGIERZ", 60.0),              # D (Bałucki Rynek) przed reformą jak B (niepewne)
])
def test_amount_is_converted_to_minutes_by_tariff_of_the_day_zone_and_discount(
        spark, ref_meters, meter, day, pln, lau, expected):
    assert paid(spark, ref_meters, meter, day, pln, lau)["mediana_minut"] == pytest.approx(expected)


@pytest.mark.parametrize("meter,zone,source", [
    ("438B", "A", "lokalizacja"),  # litera B, ale parkomat stoi w A
    ("999A", "A", "litera_id"),
    ("999B", "B", "litera_id"),
    ("999C", "B", "litera_id"),    # dawne C (Fabryczna) → B
    ("999D", "C", "litera_id"),    # D (Bałucki Rynek) → C
])
def test_subzone_comes_from_meter_location_and_letter_only_without_it(spark, ref_meters, meter, zone, source):
    p = paid(spark, ref_meters, meter, AUTUMN, "6.00")
    assert (p["podstrefa"], p["podstrefa_zrodlo"]) == (zone, source)
    assert p["mediana_minut"] is not None


def test_meter_without_letter_or_location_has_no_minutes(spark, ref_meters):
    assert paid(spark, ref_meters, "999", AUTUMN, "6.00")["mediana_minut"] is None


@pytest.mark.parametrize("paid_weeks,expected", [
    (["2025-07-08", "2025-07-15"], 1.0),  # tygodnie: [1, 1, 0] → mediana 1
    (["2025-07-08"], 0.0),                # tygodnie: [1, 0, 0] → mediana 0, jak w presji
])
def test_paid_car_hours_are_median_over_weeks_with_empty_weeks_as_zero(spark, ref_meters, paid_weeks, expected):
    amount = str(Decimal("6.00") * Decimal("0.92"))  # lato, A: 1 h
    rows = [parking("c1", "080000", day=d, amount=amount, meter="1A") for d in paid_weeks]
    rows += [tx("c2", "083000", day="2025-07-22", kod="90-002")]  # trzeci tydzień sezonu w danych
    [z] = run(spark, ref_meters, rows)["agg_parkomaty_strefy"]
    assert (z["kod"], z["blok"], z["sezon"], z["karty"]) == (ZONE, "10-13", "lato", 1)
    assert z["oplacone_autogodziny"] == pytest.approx(expected)


def test_paid_car_hours_cell_with_29_cards_is_not_exported(spark, ref_meters):
    rows = [parking(f"a{i}", "080000", meter="1A") for i in range(29)]
    rows += [parking(f"b{i}", "120000", meter="1A") for i in range(30)]
    out = run(spark, ref_meters, rows, min_cards=30)["agg_parkomaty_strefy"]
    assert [(z["blok"], z["karty"]) for z in out] == [("13-16", 30)]


def test_tariff_periods_are_contiguous_and_cover_every_zone_and_discount():
    t = pd.read_csv("data/cennik_spp.csv", parse_dates=["od", "do"])
    okresy = t.groupby("okres").agg(od=("od", "first"), do=("do", "first")).sort_values("od")
    assert okresy.index.tolist() == ["I", "II", "III"]
    assert okresy["od"].iloc[0] == pd.Timestamp("2025-01-01")
    assert (okresy["od"].iloc[1:].to_numpy() - okresy["do"].iloc[:-1].to_numpy() == pd.Timedelta(days=1)).all()
    for _, g in t.groupby("okres"):
        [podzial] = g["podzial"].unique().tolist()
        strefy = {2024: {"A", "B", "C", "D"}, 2025: {"A", "B", "C"}}[podzial]
        assert sorted(zip(g["podstrefa"], g["ulga"])) == sorted((s, u) for s in strefy for u in (0, 1))


@pytest.mark.parametrize("okres,podstrefa,ulga,stawki", [
    # zał. 4 do XIII/329/25: § 1 ust. 2 (z ulgą mieszkańca; w okresie II dla wszystkich) i ust. 3 (bez ulgi)
    ("II", "A", 0, [3.00, 6.00, 7.20, 8.60, 6.00]),
    ("II", "B", 0, [2.50, 5.00, 6.00, 7.20, 5.00]),
    ("II", "C", 0, [2.50, 5.00, 6.00, 7.20, 5.00]),
    ("III", "A", 1, [3.00, 6.00, 7.20, 8.60, 6.00]),
    ("III", "A", 0, [3.50, 6.90, 8.20, 9.80, 6.90]),
    ("III", "B", 1, [2.50, 5.00, 6.00, 7.20, 5.00]),
    ("III", "B", 0, [3.00, 6.00, 7.20, 8.60, 6.00]),
    ("III", "C", 1, [2.50, 5.00, 6.00, 7.20, 5.00]),  # bilet 0,00 zł (30 min raz dziennie) nie trafia do Visa
    ("III", "C", 0, [3.00, 6.00, 7.20, 8.60, 6.00]),
])
def test_tariff_matches_attachment_4_of_resolution(okres, podstrefa, ulga, stawki):
    t = pd.read_csv("data/cennik_spp.csv")
    [row] = t[(t["okres"] == okres) & (t["podstrefa"] == podstrefa) & (t["ulga"] == ulga)].to_dict("records")
    assert [row[c] for c in ["stawka_30min", "h1", "h2", "h3", "h4"]] == stawki


# ---------- ticket 08: karty kierowców i cel wizyty po opłacie ----------

@pytest.mark.parametrize("kod,from_payment", [("90-002", True), ("90-009", False)],
                         ids=["kod_w_zasiegu_500m", "kod_poza_zasiegiem"])
def test_purchase_within_meter_reach_starts_visit_at_payment(spark, ref, kod, from_payment):
    reach = spark.createDataFrame([("438B", ZONE), ("438B", "90-002")], "numer string, kod_pocztowy string")
    rows = [parking("c1", "080000", meter="438B"), tx("c1", "090000", mcc=5462, name="PIEKARNIA", kod=kod)]
    [g] = run(spark, replace(ref, meter_reach=reach), rows)["agg_grupy"]
    assert g["kod"] == kod and g["blok"] == "10-13"
    assert g["mediana_czasu_wizyty_min"] == (60 + 15 if from_payment else 15)


def test_meter_outside_reach_table_falls_back_to_its_own_code(spark, ref):
    reach = spark.createDataFrame([("999A", "90-002")], "numer string, kod_pocztowy string")
    rows = [parking("c1", "080000", meter="438B"), tx("c1", "090000", mcc=5462, name="PIEKARNIA")]
    [g] = run(spark, replace(ref, meter_reach=reach), rows)["agg_grupy"]
    assert g["mediana_czasu_wizyty_min"] == 60 + 15


@pytest.mark.parametrize("mcc", [5541, 5542])
def test_fuel_station_is_not_a_visit_target(spark, ref, mcc):
    # Stacja paliw w mapowaniu grup, żeby sprawdzić jawne wykluczenie, a nie brak grupy.
    groups = ref.mcc_groups.unionByName(
        spark.createDataFrame([(mcc, "handel", 15)], "mcc int, grupa string, czas_domyslny_min int"))
    rows = [parking("c1", "080000", meter="438B"), tx("c1", "083000", mcc=mcc, name="ORLEN STACJA")]
    out = run(spark, replace(ref, mcc_groups=groups), rows)
    assert out["agg_grupy"] == [] and out["agg_strefy"] == []


def test_payment_via_app_or_private_parking_makes_a_driver_card(spark, ref):
    rows = [
        tx("c1", "080000", mcc=7523, name="FLOWBIRD APP", kod="93-020", cp=0, channel="mobile"),
        tx("c1", "083000"),
        tx("c2", "080000", mcc=7523, name="PARKING UMED", kod="90-419"),
        tx("c2", "083000"),
        tx("c3", "083000"),
    ]
    [g] = run(spark, ref, rows)["agg_grupy"]
    assert g["karty_przyjezdne"] == 3
    assert g["wspolczynnik_kierowcow"] == pytest.approx(2 / 3)
    assert g["mediana_czasu_wizyty_min"] == 75  # opłata bez lokalizacji nie przesuwa startu wizyty


def test_buffer_zone_uses_driver_share_measured_in_spp(spark, ref):
    buffer = "90-002"
    rows = [
        parking("c1", "080000"), tx("c1", "083000"),  # SPP: kierowca
        tx("c2", "083000"),                            # SPP: bez opłaty → d_SPP = 1/2
        tx("c3", "083000", kod=buffer),                # bufor: nikt nie płaci (darmowy parking)
        tx("c4", "083000", kod=buffer),
    ]
    by_kod = {g["kod"]: g for g in run(spark, replace(ref, spp_codes=[ZONE]), rows)["agg_grupy"]}
    assert by_kod[ZONE]["spp"] is True and by_kod[buffer]["spp"] is False
    assert by_kod[ZONE]["wspolczynnik_kierowcow"] == pytest.approx(0.5)
    assert by_kod[buffer]["wspolczynnik_kierowcow"] == pytest.approx(0.5)
