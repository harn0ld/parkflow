"""Etap 2: transakcje Łodzi (poziom karty) → agregaty bez identyfikatorów kart.

Jedno wejście (transakcje + dane referencyjne), jedno wyjście (słownik agregatów).
Poziom karty nie opuszcza `build_aggregates` (SPEC §7).

Wyjście:
- `agg_grupy`     kod × blok × sezon × grupa: karty przyjezdne, współczynnik kierowców,
                  mediana czasu wizyty, presja grupy (mediana po tygodniach), flaga SPP.
- `agg_strefy`    kod × blok × sezon: presja = mediana po tygodniach Σ grup; komórki < 30 kart
                  mają `za_malo_danych = true` i puste liczby.
- `agg_parkomaty` parkomat × okres × blok: opłacony czas postoju, auto-godziny, rotacja.
- `agg_parkomaty_strefy` kod × blok × sezon: zmierzony popyt = mediana po tygodniach opłaconych auto-godzin
                  (tygodnie bez opłat = 0), karty ≥ 30; wymaga kodu parkomatu z data/parkomaty.csv.
- `agg_spp_okres` okres × blok × podstrefa: naturalny eksperyment dla całej SPP.
- `agg_stali`     parkomat × sezon: udział stałych bywalców.
- `kody_zbiorcze` kody z > 400 sprzedawcami (adresy rozliczeniowe), wyłączone ze stref.
- `agg_kalibracja_czasow` grupa: mediana zmierzonego czasu (pierwsza → ostatnia transakcja) wizyt
                  wielotransakcyjnych vs czas domyślny grupy; grupy z ≥ 30 kartami.

Użycie:
    python -m pipeline.aggregate <lodz_all.parquet> <katalog_wyjściowy> [--miasto krakow] [--data KATALOG]

`--data` to dane referencyjne miasta (domyślnie katalog miasta z `parkflow.miasta`); grupy MCC
i wykluczenia nazw, jeśli ich tam brak, są brane ze wspólnego `data/`.
"""

import argparse
import csv
import os
from dataclasses import dataclass, field
from datetime import date

from pyspark.sql import Column, DataFrame, SparkSession, Window
from pyspark.sql import functions as F

from parkflow.miasta import DANE, LODZ, MIASTA, Miasto
from pipeline.spark import get_spark

MIN_CARDS = 30
# Kod z > 400 różnymi sprzedawcami to kod zbiorczy (prawdziwe miejsca, np. Manufaktura, mają ≤ ~200).
HUB_MIN_MERCHANTS = 400
AMOUNT_FACTOR = 0.92
VISIT_GAP_MIN = 90
AFTER_PAYMENT_WINDOW_MIN = 180
REGULAR_MIN_DAYS_PER_WEEK = 3
REGULAR_MIN_PAID_MIN = 240

# Dni robocze bez opłat w SPP (święta pn–pt w zakresie danych); Boże Ciało 19.06.2025 wg SPEC §3.1.
HOLIDAYS = [
    "2025-01-01", "2025-01-06", "2025-04-21", "2025-05-01", "2025-06-19", "2025-08-15",
    "2025-11-11", "2025-12-24", "2025-12-25", "2025-12-26", "2026-01-01", "2026-01-06",
    "2026-04-06", "2026-05-01", "2026-06-04",
]

# (okres, od, do) — okres przed reformą służy tylko do naturalnego eksperymentu.
PERIODS = [
    ("przed_reforma", "2025-01-01", "2025-05-31"),
    ("lato", "2025-06-01", "2025-09-30"),
    ("rok_akademicki", "2025-10-01", "2026-06-30"),
]
SEASONS = ["lato", "rok_akademicki"]

BLOCKS = [("07-10", 7, 10), ("10-13", 10, 13), ("13-16", 13, 16), ("16-19", 16, 19)]

EXCLUDED_MCC = [7523, 4111, 4784]
# Stacje paliw mają własny plac: nie są celem wizyty po opłacie (SPEC §4.2) ani wizytą w strefie.
FUEL_MCC = [5541, 5542]
# Wartości z danych: Tap to pay / Manual key entry / COF / Chip / Magstripe / Other.
MANUAL_ENTRY_MODES = ["Manual key entry", "COF"]
# channel_flg: e-commerce, płatności cykliczne, zamówienia pocztowe/telefoniczne.
REMOTE_CHANNELS = ["eci", "recur", "moto"]


@dataclass
class Reference:
    mcc_groups: DataFrame  # mcc, grupa, czas_domyslny_min
    tariff: DataFrame  # od, do, [podzial], podstrefa, ulga, stawka_30min, h1..h4
    exclusions: list[str]  # regexy na mrch_nm_raw (dostawy, duże formaty)
    meters: DataFrame | None = None  # numer, podstrefa, [podstrefa_2024], kod_pocztowy (opcjonalnie)
    spp_codes: list[str] | None = None  # kody pocztowe obecnej SPP (opcjonalnie)
    excluded_codes: list[str] = field(default_factory=list)  # kody galerii z własnym parkingiem
    meter_reach: DataFrame | None = None  # numer, kod_pocztowy: kody ~500 m od parkomatu (opcjonalnie)
    meter_pattern: str = LODZ.parkomat_regex  # mrch_nm_raw → numer parkomatu SPP (grupa 1)
    resident_lau: str | None = LODZ.lau_ulgi  # lau_enr ze stawką ulgową; None = wszyscy bez ulgi
    foreign_parking: str | None = None  # nazwy 7523 z innych miast rozliczane pod kodami miasta


def load_reference(spark: SparkSession, data_dir: str, miasto: Miasto = LODZ, shared_dir: str = str(DANE)) -> Reference:
    def path_of(name: str, shared: bool = False) -> str:
        path = os.path.join(data_dir, name)
        return os.path.join(shared_dir, name) if shared and not os.path.exists(path) else path

    def csv_df(name: str, shared: bool = False) -> DataFrame | None:
        path = path_of(name, shared)
        if not os.path.exists(path):
            return None
        return spark.read.csv(path, header=True, inferSchema=True)

    with open(path_of("wykluczenia.csv", shared=True), newline="") as f:
        exclusions = [row["wzorzec"] for row in csv.DictReader(f)]
    spp = csv_df("spp_kody.csv")
    excluded = csv_df("wykluczenia_kody.csv")
    meters = csv_df("parkomaty.csv")
    if meters is not None:
        meters = meters.select(
            F.upper(F.col("numer").cast("string")).alias("numer"),
            "podstrefa",
            F.col("podstrefa_2024").cast("string").alias("podstrefa_2024")
            if "podstrefa_2024" in meters.columns
            else F.lit(None).cast("string").alias("podstrefa_2024"),
            F.col("kod_pocztowy").cast("string").alias("kod_pocztowy")
            if "kod_pocztowy" in meters.columns
            else F.lit(None).cast("string").alias("kod_pocztowy"),
        )
    reach = csv_df("parkomaty_zasieg.csv")
    if reach is not None:
        reach = reach.select(F.upper(F.col("numer").cast("string")).alias("numer"),
                             F.col("kod_pocztowy").cast("string").alias("kod_pocztowy"))
    return Reference(
        mcc_groups=csv_df("mcc_groups.csv", shared=True).select("mcc", "grupa", "czas_domyslny_min"),
        tariff=csv_df("cennik_spp.csv"),
        exclusions=exclusions,
        meters=meters,
        spp_codes=[r["kod_pocztowy"] for r in spp.collect()] if spp is not None else None,
        excluded_codes=[r["kod_pocztowy"] for r in excluded.collect()] if excluded is not None else [],
        meter_reach=reach,
        meter_pattern=miasto.parkomat_regex,
        resident_lau=miasto.lau_ulgi,
        foreign_parking=miasto.parkingi_obce,
    )


# ---------- czas ----------

def _with_local_time(df: DataFrame) -> DataFrame:
    utc = F.to_timestamp(F.concat_ws(" ", "prch_dt", "tran_id_gmt_tm"), "yyyy-MM-dd HHmmss")
    local = F.from_utc_timestamp(utc, "Europe/Warsaw")
    hour = F.hour(local)
    block = F.lit(None).cast("string")
    for name, start, end in reversed(BLOCKS):
        block = F.when((hour >= start) & (hour < end), name).otherwise(block)
    period = F.lit(None).cast("string")
    for name, start, end in reversed(PERIODS):
        period = F.when(F.to_date(local).between(start, end), name).otherwise(period)
    return (
        df.where(F.col("tran_id_gmt_tm") != "000000")
        .withColumn("ts", local)
        .withColumn("day", F.to_date(local))
        .withColumn("week", F.date_trunc("week", local).cast("date"))
        .withColumn("block", block)
        .withColumn("period", period)
        .withColumn(
            "workday",
            (F.dayofweek(local).between(2, 6)) & ~F.to_date(local).isin(*[date.fromisoformat(d) for d in HOLIDAYS]),
        )
    )


def _minutes_between(a: Column, b: Column) -> Column:
    return (F.unix_timestamp(b) - F.unix_timestamp(a)) / 60.0


# ---------- opłaty parkingowe ----------

def _parking(tx: DataFrame, ref: Reference) -> DataFrame:
    """Wszystkie opłaty 7523 (także cp_flag = 0) z minutami dla parkomatów SPP.

    Minuty: kwota / 0,92 → cennik z dnia transakcji, podstrefy parkomatu i ulgi (`lau_enr = ref.resident_lau`),
    odwrócone naliczanie proporcjonalne (zał. 4 § 1 ust. 4). Wiersze cennika z `podzial = 2024`
    (okres I, przed reformą) dotyczą podstref z mapy 2024 (`podstrefa_2024`: A, B, C = Fabryczna,
    D = Bałucki Rynek), pozostałe — obecnych podstref A/B/C.
    """
    p = tx.where(F.col("mrch_catg_cd") == 7523)
    if ref.foreign_parking:
        p = p.where(~F.upper(F.coalesce(F.col("mrch_nm_raw"), F.lit(""))).rlike(ref.foreign_parking))
    meter_id = F.regexp_extract(F.upper(F.trim(F.col("mrch_nm_raw"))), ref.meter_pattern, 1)
    p = p.withColumn("parkomat", F.when(meter_id != "", meter_id))
    if ref.meters is not None:
        p = p.join(
            ref.meters.withColumnRenamed("numer", "parkomat").withColumnRenamed("kod_pocztowy", "parkomat_kod"),
            "parkomat",
            "left",
        )
    else:
        p = (p.withColumn("podstrefa", F.lit(None).cast("string"))
             .withColumn("podstrefa_2024", F.lit(None).cast("string"))
             .withColumn("parkomat_kod", F.lit(None).cast("string")))
    if "podstrefa_2024" not in p.columns:
        p = p.withColumn("podstrefa_2024", F.lit(None).cast("string"))
    # Bez lokalizacji parkomatu: litera z ID wg mapy 2024 (dawne C → B, D = Bałucki Rynek → C).
    letter = F.regexp_extract(F.col("parkomat"), r"([A-Z])$", 1)
    from_letter = F.when(letter == "A", "A").when(letter.isin("B", "C"), "B").when(letter == "D", "C")
    p = (
        p.withColumn("podstrefa_zrodlo", F.when(F.col("podstrefa").isNotNull(), "lokalizacja").when(
            F.col("parkomat").isNotNull(), "litera_id"))
        .withColumn("podstrefa", F.coalesce(F.col("podstrefa"), from_letter))
        .withColumn("podstrefa_2024", F.coalesce(
            F.col("podstrefa_2024"), F.when(letter.isin("A", "B", "C", "D"), letter)))
        .withColumn("ulga", F.when(F.upper(F.trim(F.col("lau_enr"))) == ref.resident_lau, 1).otherwise(0)
                    if ref.resident_lau else F.lit(0))
        .withColumn("kwota_pln", F.round(F.col("cs_tran_amt").cast("double") / AMOUNT_FACTOR, 2))
    )
    division = F.col("podzial").cast("int") if "podzial" in ref.tariff.columns else F.lit(2025)
    t = ref.tariff.select(
        F.col("od").cast("date").alias("t_od"), F.col("do").cast("date").alias("t_do"), division.alias("t_podzial"),
        F.col("podstrefa").alias("t_podstrefa"), F.col("ulga").alias("t_ulga"),
        *[F.col(c).cast("double").alias(c) for c in ["stawka_30min", "h1", "h2", "h3", "h4"]],
    )
    p = p.join(
        F.broadcast(t),
        (F.col("day").between(F.col("t_od"), F.col("t_do")))
        & (F.when(F.col("t_podzial") == 2024, F.col("podstrefa_2024")).otherwise(F.col("podstrefa"))
           == F.col("t_podstrefa"))
        & (F.col("ulga") == F.col("t_ulga")),
        "left",
    )
    a = F.col("kwota_pln")
    c1 = F.col("h1")
    c2 = c1 + F.col("h2")
    c3 = c2 + F.col("h3")
    minutes = (
        F.when(a <= F.col("stawka_30min"), 30.0)
        .when(a <= c1, 60 * a / F.col("h1"))
        .when(a <= c2, 60 + 60 * (a - c1) / F.col("h2"))
        .when(a <= c3, 120 + 60 * (a - c2) / F.col("h3"))
        .otherwise(180 + 60 * (a - c3) / F.col("h4"))
    )
    return p.withColumn("minuty", F.when(F.col("parkomat").isNotNull() & F.col("h1").isNotNull(), F.round(minutes, 1)))


# ---------- wizyty ----------

def _visit_transactions(tx: DataFrame, ref: Reference) -> DataFrame:
    exclude = "|".join(f"(?:{p})" for p in ref.exclusions)
    return (
        tx.where(F.col("transaction_type").isin("POS", "ATM"))
        .where(F.col("cp_flag") == 1)
        .where(~F.coalesce(F.col("channel_flg"), F.lit("")).isin(*REMOTE_CHANNELS))
        .where(~F.coalesce(F.col("transaction_pos_entry_mode"), F.lit("")).isin(*MANUAL_ENTRY_MODES))
        .where(~F.col("mrch_catg_cd").isin(*EXCLUDED_MCC, *FUEL_MCC))
        .where(~F.upper(F.coalesce(F.col("mrch_nm_raw"), F.lit(""))).rlike(exclude))
        .where(F.col("kod").isNotNull())
        .join(F.broadcast(ref.mcc_groups.withColumnRenamed("mcc", "mrch_catg_cd")), "mrch_catg_cd")
    )


def _payment_reach(parking: DataFrame, reach: DataFrame | None) -> DataFrame:
    """Opłaty SPP × kody, w których zakup może być celem wizyty po tej opłacie.

    Promień ~500 m przybliża tabela `data/parkomaty_zasieg.csv` (`pipeline/zasieg.py`): kody, których
    polygon jest ≤ 500 m od parkomatu, a dla parkomatu z kodem bez lokalizacji ten sam lub sąsiedni kod.
    Parkomat spoza tabeli (albo brak tabeli) → tylko kod parkomatu. Aplikacje, parkingi prywatne
    i parkomaty bez kodu nie wskazują miejsca: nie wyznaczają startu wizyty.
    """
    pay = parking.where(F.col("parkomat").isNotNull()).select(
        F.col("card").alias("p_card"), F.col("day").alias("p_day"), "parkomat", "parkomat_kod",
        F.col("ts").alias("p_ts"),
    )
    if reach is None:
        return pay.select("p_card", "p_day", F.col("parkomat_kod").alias("p_kod"), "p_ts").where(
            F.col("p_kod").isNotNull())
    r = F.broadcast(reach.select(F.col("numer").alias("parkomat"), F.col("kod_pocztowy").alias("r_kod")))
    in_table = pay.join(r, "parkomat").select("p_card", "p_day", F.col("r_kod").alias("p_kod"), "p_ts")
    own = pay.join(r.select("parkomat").distinct(), "parkomat", "left_anti").select(
        "p_card", "p_day", F.col("parkomat_kod").alias("p_kod"), "p_ts")
    return in_table.unionByName(own).where(F.col("p_kod").isNotNull())


def _visits(vt: DataFrame, parking: DataFrame, reach: DataFrame | None = None) -> DataFrame:
    """Sklejanie transakcji karty w wizyty: ten sam kod i dzień, przerwa ≤ 90 min."""
    w = Window.partitionBy("card", "day", "kod").orderBy("ts", "tran_id_raw")
    v = (
        vt.withColumn("prev_ts", F.lag("ts").over(w))
        .withColumn("new_visit", F.when(
            F.col("prev_ts").isNull() | (_minutes_between(F.col("prev_ts"), F.col("ts")) > VISIT_GAP_MIN), 1
        ).otherwise(0))
        .withColumn("visit_no", F.sum("new_visit").over(w.rowsBetween(Window.unboundedPreceding, 0)))
    )
    visits = v.groupBy("card", "day", "week", "period", "kod", "visit_no").agg(
        F.min("ts").alias("start"),
        F.max("ts").alias("end"),
        F.max_by("grupa", F.struct("ts", "tran_id_raw")).alias("grupa"),
        F.max_by("czas_domyslny_min", F.struct("ts", "tran_id_raw")).alias("czas_domyslny_min"),
        F.max("przyjezdny").alias("przyjezdny"),
        F.count("*").alias("transakcje"),
    )
    # Wizyta po opłacie: ostatnia opłata SPP karty ~500 m od kodu wizyty, 0–180 min przed pierwszą
    # transakcją. Stacje paliw odpadają wcześniej (`FUEL_MCC` w `_visit_transactions`).
    pay = _payment_reach(parking, reach)
    starts = (
        visits.join(
            pay,
            (F.col("card") == F.col("p_card")) & (F.col("day") == F.col("p_day")) & (F.col("kod") == F.col("p_kod"))
            & (F.col("p_ts") <= F.col("start"))
            & (_minutes_between(F.col("p_ts"), F.col("start")) <= AFTER_PAYMENT_WINDOW_MIN),
            "left",
        )
        .groupBy(*visits.columns)
        .agg(F.max("p_ts").alias("p_ts"))
    )
    start = F.coalesce(F.col("p_ts"), F.col("start"))
    hour = F.hour(start)
    block = F.lit(None).cast("string")
    for name, s, e in reversed(BLOCKS):
        block = F.when((hour >= s) & (hour < e), name).otherwise(block)
    return (
        starts.withColumn("block", block)
        .withColumn("czas_wizyty_min", _minutes_between(start, F.col("end")) + F.col("czas_domyslny_min"))
        .drop("p_ts")
    )


# ---------- agregaty ----------

def _weeks(tx: DataFrame) -> DataFrame:
    return tx.where(F.col("period").isin(*SEASONS) & F.col("workday")).select(
        F.col("period").alias("sezon"), "week"
    ).distinct()


def build_aggregates(
    tx: DataFrame, ref: Reference, min_cards: int = MIN_CARDS, hub_min_merchants: int = HUB_MIN_MERCHANTS
) -> dict[str, DataFrame]:
    tx = _with_local_time(tx.withColumnRenamed("pymt_crd_acct_num_raw", "card").withColumnRenamed(
        "mrch_postal_code", "kod"))
    parking = _parking(tx, ref)

    # Kody zbiorcze: adres agenta rozliczeniowego, nie miejsce (np. dziesiątki Lidli pod 91-111).
    hubs = (
        tx.where(F.col("kod").isNotNull()).groupBy("kod")
        .agg(F.countDistinct("mrch_nm_raw").alias("sprzedawcy"), F.count("*").alias("transakcje"))
        .where(F.col("sprzedawcy") > hub_min_merchants)
    )

    driver_days = parking.select("card", "day").distinct().withColumn("kierowca", F.lit(1))
    local_tx = tx.join(F.broadcast(hubs.select("kod")), "kod", "left_anti").where(
        ~F.col("kod").isin(*ref.excluded_codes) if ref.excluded_codes else F.lit(True)
    )
    vt = _visit_transactions(local_tx.where(F.col("period").isin(*SEASONS) & F.col("workday")), ref).withColumn(
        "przyjezdny", F.when(F.col("pstl_cd_enr").isNull() | (F.col("pstl_cd_enr") != F.col("kod")), 1).otherwise(0)
    )
    visits = (
        _visits(vt, parking, ref.meter_reach)
        .where(F.col("block").isNotNull() & (F.col("przyjezdny") == 1))
        .join(driver_days, ["card", "day"], "left")
        .withColumn("kierowca", F.coalesce("kierowca", F.lit(0)))
        .withColumnRenamed("period", "sezon")
        .cache()
    )

    cell = ["kod", "block", "sezon", "grupa"]
    spp_flag = (
        F.col("kod").isin(*ref.spp_codes) if ref.spp_codes is not None else F.lit(None).cast("boolean")
    )

    # Współczynnik kierowców: odsetek par karta×dzień przyjezdnych z opłatą parkingową w mieście.
    d_zone = visits.groupBy("kod", "sezon", "grupa").agg(
        (F.countDistinct(F.when(F.col("kierowca") == 1, F.struct("card", "day")))
         / F.countDistinct("card", "day")).alias("d_strefa")
    )
    d = d_zone.withColumn("spp", spp_flag)
    if ref.spp_codes is not None:
        # W buforze stosujemy współczynnik policzony w SPP (dolne oszacowanie, SPEC §4.1).
        d_spp = visits.where(F.col("kod").isin(*ref.spp_codes)).groupBy("sezon", "grupa").agg(
            (F.countDistinct(F.when(F.col("kierowca") == 1, F.struct("card", "day")))
             / F.countDistinct("card", "day")).alias("d_spp")
        )
        d = d.join(d_spp, ["sezon", "grupa"], "left").withColumn(
            "wspolczynnik_kierowcow", F.when(F.col("spp"), F.col("d_strefa")).otherwise(F.col("d_spp"))
        )
    else:
        d = d.withColumn("wspolczynnik_kierowcow", F.col("d_strefa"))
    d = d.select("kod", "sezon", "grupa", "spp", "wspolczynnik_kierowcow")

    season_cells = visits.groupBy(*cell).agg(
        F.countDistinct("card").alias("karty_przyjezdne"),
        F.percentile_approx("czas_wizyty_min", 0.5).alias("mediana_czasu_wizyty_min"),
    ).join(d, ["kod", "sezon", "grupa"])

    # Presja tygodniowa grupy; tygodnie bez wizyt liczą się jako 0.
    weekly = visits.groupBy(*cell, "week").agg(F.countDistinct("card").alias("karty_tydz"))
    weeks = _weeks(tx)
    grid = season_cells.select(*cell).join(weeks, "sezon")
    weekly = (
        grid.join(weekly, [*cell, "week"], "left")
        .fillna(0, ["karty_tydz"])
        .join(season_cells.select(*cell, "wspolczynnik_kierowcow", "mediana_czasu_wizyty_min"), cell)
        .withColumn(
            "presja_tydz",
            F.col("karty_tydz") * F.coalesce("wspolczynnik_kierowcow", F.lit(0.0))
            * F.col("mediana_czasu_wizyty_min") / 60.0,
        )
    )
    group_pressure = weekly.groupBy(*cell).agg(F.percentile_approx("presja_tydz", 0.5).alias("presja"))
    agg_grupy = (
        season_cells.join(group_pressure, cell)
        .where(F.col("karty_przyjezdne") >= min_cards)
        .select(*cell, "karty_przyjezdne", "wspolczynnik_kierowcow", "mediana_czasu_wizyty_min", "presja", "spp")
    )

    zone = ["kod", "block", "sezon"]
    zone_cards = visits.groupBy(*zone).agg(F.countDistinct("card").alias("karty_przyjezdne"))
    zone_pressure = (
        weekly.groupBy(*zone, "week").agg(F.sum("presja_tydz").alias("presja_tydz"))
        .groupBy(*zone).agg(F.percentile_approx("presja_tydz", 0.5).alias("presja"))
    )
    enough = F.col("karty_przyjezdne") >= min_cards
    agg_strefy = (
        zone_cards.join(zone_pressure, zone)
        .withColumn("spp", spp_flag)
        .select(
            *zone,
            F.when(enough, F.col("karty_przyjezdne")).alias("karty_przyjezdne"),
            F.when(enough, F.col("presja")).alias("presja"),
            (~enough).alias("za_malo_danych"),
            "spp",
        )
    )

    # ---- parkomaty ----
    spp_pay = parking.where(F.col("parkomat").isNotNull() & F.col("period").isNotNull() & F.col("workday")
                            & F.col("block").isNotNull()).cache()
    meter_cell = ["parkomat", "period", "block"]
    meter_weekly = spp_pay.groupBy(*meter_cell, "week").agg((F.sum("minuty") / 60).alias("autogodziny_tydz"))
    agg_parkomaty = (
        spp_pay.groupBy(*meter_cell).agg(
            F.first("podstrefa").alias("podstrefa"),
            F.first("podstrefa_zrodlo").alias("podstrefa_zrodlo"),
            F.first("parkomat_kod").alias("kod"),
            F.count("*").alias("platnosci"),
            F.countDistinct("card").alias("karty"),
            F.countDistinct("day").alias("dni_z_platnoscia"),
            F.percentile_approx("minuty", 0.5).alias("mediana_minut"),
            F.avg("minuty").alias("srednia_minut"),
            F.avg("kwota_pln").alias("srednia_kwota_pln"),
        )
        .join(meter_weekly.groupBy(*meter_cell).agg(
            F.percentile_approx("autogodziny_tydz", 0.5).alias("autogodziny_tydz_mediana")), meter_cell)
        .withColumn("platnosci_na_dzien", F.col("platnosci") / F.col("dni_z_platnoscia"))
        .where(F.col("karty") >= min_cards)
        .withColumnRenamed("period", "okres")
    )

    # Naturalny eksperyment na poziomie całej SPP (parkomaty rzadko przekraczają próg 30 kart).
    spp_cell = ["period", "block", "podstrefa"]
    agg_spp_okres = (
        spp_pay.groupBy(*spp_cell).agg(
            F.count("*").alias("platnosci"),
            F.countDistinct("card").alias("karty"),
            F.countDistinct("parkomat").alias("parkomaty"),
            F.countDistinct("day").alias("dni_robocze"),
            F.percentile_approx("minuty", 0.5).alias("mediana_minut"),
            F.avg("minuty").alias("srednia_minut"),
            F.avg((F.col("minuty") > 120).cast("double")).alias("udzial_powyzej_2h"),
            F.avg("kwota_pln").alias("srednia_kwota_pln"),
        )
        .withColumn("platnosci_na_parkomat_dzien", F.col("platnosci") / (F.col("parkomaty") * F.col("dni_robocze")))
        .where(F.col("karty") >= min_cards)
        .withColumnRenamed("period", "okres")
    )

    # Zmierzony popyt: mediana po tygodniach roboczych sezonu z opłaconych auto-godzin; tygodnie bez opłat
    # liczą się jako 0 — tak samo jak w presji, żeby obie miary były porównywalne.
    paid_zone = ["kod", "block", "sezon"]
    zone_pay = spp_pay.where(F.col("parkomat_kod").isNotNull() & F.col("period").isin(*SEASONS)).select(
        F.col("parkomat_kod").alias("kod"), "block", F.col("period").alias("sezon"), "week", "card", "minuty")
    zone_cards = zone_pay.groupBy(*paid_zone).agg(F.countDistinct("card").alias("karty"))
    zone_paid_weekly = zone_pay.groupBy(*paid_zone, "week").agg((F.sum("minuty") / 60).alias("autogodziny_tydz"))
    agg_parkomaty_strefy = (
        zone_cards.select(*paid_zone).join(_weeks(tx), "sezon")
        .join(zone_paid_weekly, [*paid_zone, "week"], "left")
        .fillna(0.0, ["autogodziny_tydz"])
        .groupBy(*paid_zone).agg(F.percentile_approx("autogodziny_tydz", 0.5).alias("oplacone_autogodziny"))
        .join(zone_cards, paid_zone)
        .where(F.col("karty") >= min_cards)
        .select(*paid_zone, "oplacone_autogodziny", "karty")
    )

    # Stali bywalcy: ≥ 3 dni robocze w tygodniu z opłaconym postojem > 4 h przy tym samym parkomacie.
    long_days = (
        spp_pay.where(F.col("period").isin(*SEASONS))
        .groupBy("card", "parkomat", "period", "week", "day").agg(F.sum("minuty").alias("min_dzien"))
        .where(F.col("min_dzien") > REGULAR_MIN_PAID_MIN)
    )
    regulars = (
        long_days.groupBy("card", "parkomat", "period", "week").agg(F.count("*").alias("dni"))
        .where(F.col("dni") >= REGULAR_MIN_DAYS_PER_WEEK)
        .select("card", "parkomat", "period").distinct().withColumn("staly", F.lit(1))
    )
    agg_stali = (
        spp_pay.where(F.col("period").isin(*SEASONS)).select("card", "parkomat", "period", "parkomat_kod").distinct()
        .join(regulars, ["card", "parkomat", "period"], "left")
        .groupBy("parkomat", F.col("period").alias("sezon"))
        .agg(
            F.first("parkomat_kod").alias("kod"),
            F.countDistinct("card").alias("karty"),
            F.round(F.countDistinct(F.when(F.col("staly") == 1, F.col("card"))) / F.countDistinct("card"), 2)
            .alias("udzial_stalych"),
        )
        .where(F.col("karty") >= min_cards)
    )

    # Kalibracja czasów domyślnych: zmierzony czas wizyt z ≥ 2 transakcjami (bez startu od opłaty),
    # grupa wizyty = grupa ostatniej transakcji, jak w czasie wizyty.
    multi = visits.where(F.col("transakcje") >= 2)
    agg_kalibracja_czasow = (
        multi.groupBy("grupa").agg(
            F.first("czas_domyslny_min").alias("czas_domyslny_min"),
            F.count("*").alias("wizyty_wielotransakcyjne"),
            F.countDistinct("card").alias("karty"),
            F.percentile_approx(_minutes_between(F.col("start"), F.col("end")), 0.5)
            .alias("mediana_czasu_zmierzonego_min"),
        )
        .join(visits.groupBy("grupa").agg(F.count("*").alias("wizyty")), "grupa")
        .withColumn("udzial_wielotransakcyjnych", F.col("wizyty_wielotransakcyjne") / F.col("wizyty"))
        .where(F.col("karty") >= min_cards)
        .select("grupa", "czas_domyslny_min", "wizyty_wielotransakcyjne", "karty", "udzial_wielotransakcyjnych",
                "mediana_czasu_zmierzonego_min")
    )

    out = {
        "agg_grupy": agg_grupy,
        "agg_strefy": agg_strefy,
        "agg_parkomaty": agg_parkomaty,
        "agg_spp_okres": agg_spp_okres,
        "kody_zbiorcze": hubs,
        "agg_parkomaty_strefy": agg_parkomaty_strefy,
        "agg_stali": agg_stali,
        "agg_kalibracja_czasow": agg_kalibracja_czasow,
    }
    return {name: df.withColumnRenamed("block", "blok") for name, df in out.items()}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--miasto", default=LODZ.id, choices=sorted(MIASTA))
    ap.add_argument("--data", default=None, help="dane referencyjne (domyślnie katalog miasta)")
    args = ap.parse_args()
    miasto = MIASTA[args.miasto]
    spark = get_spark(f"parkflow-aggregate-{miasto.id}")
    ref = load_reference(spark, args.data or str(miasto.katalog), miasto)
    os.makedirs(args.dst, exist_ok=True)
    for name, df in build_aggregates(spark.read.parquet(args.src), ref).items():
        # Agregaty są małe: jeden plik .parquet zamiast katalogu Sparka.
        path = os.path.join(args.dst, f"{name}.parquet")
        pdf = df.toPandas()
        pdf.to_parquet(path, index=False)
        print(f"{name}: {len(pdf):,} wierszy → {path}")


if __name__ == "__main__":
    main()
