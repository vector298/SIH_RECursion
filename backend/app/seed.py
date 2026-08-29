"""Seed a fictional corpus.

    python -m app.seed --records 1500 --reset

Everything here is invented. No real missing-person record, name, or image is
used or reproduced. The corpus exists so the hard-search funnel has something
real to reduce — running the pipeline against six records proves nothing.

A deliberately planted pair (CASE-2026-0147 / CASE-2026-0304) shares an
eyebrow scar, a forearm birthmark and a plausible transit corridor, so the
matcher has a genuine signal to find rather than noise to rank.
"""
from __future__ import annotations

import argparse
import random
from datetime import date, datetime, timedelta

from sqlalchemy import delete, select

from app.core import semantic
from app.db.models import (
    AdaptiveQuestion, AuditLog, Candidate, Case, Image, Mark, MatchRun, Verification,
)
from app.db.session import SessionLocal, engine, init_db

CITIES = [
    ("Bengaluru", "Bengaluru Urban", "Karnataka", 12.9716, 77.5946),
    ("Chennai", "Chennai", "Tamil Nadu", 13.0827, 80.2707),
    ("Pune", "Pune City", "Maharashtra", 18.5204, 73.8567),
    ("Mumbai", "Mumbai Suburban", "Maharashtra", 19.0760, 72.8777),
    ("Kochi", "Ernakulam", "Kerala", 9.9312, 76.2673),
    ("Hyderabad", "Hyderabad", "Telangana", 17.3850, 78.4867),
    ("Jaipur", "Jaipur", "Rajasthan", 26.9124, 75.7873),
    ("Vijayawada", "Krishna", "Andhra Pradesh", 16.5062, 80.6480),
    ("Nagpur", "Nagpur", "Maharashtra", 21.1458, 79.0882),
    ("Mysuru", "Mysuru", "Karnataka", 12.2958, 76.6394),
    ("Coimbatore", "Coimbatore", "Tamil Nadu", 11.0168, 76.9558),
    ("Ahmedabad", "Ahmedabad", "Gujarat", 23.0225, 72.5714),
    ("Patna", "Patna", "Bihar", 25.5941, 85.1376),
    ("Kolkata", "Kolkata", "West Bengal", 22.5726, 88.3639),
    ("New Delhi", "New Delhi", "Delhi", 28.6139, 77.2090),
    ("Guwahati", "Kamrup Metropolitan", "Assam", 26.1445, 91.7362),
    ("Amritsar", "Amritsar", "Punjab", 31.6340, 74.8723),
    ("Lucknow", "Lucknow", "Uttar Pradesh", 26.8467, 80.9462),
    ("Bhopal", "Bhopal", "Madhya Pradesh", 23.2599, 77.4126),
    ("Surat", "Surat", "Gujarat", 21.1702, 72.8311),
    ("Ranchi", "Ranchi", "Jharkhand", 23.3441, 85.3096),
    ("Bhubaneswar", "Khordha", "Odisha", 20.2961, 85.8245),
    ("Dehradun", "Dehradun", "Uttarakhand", 30.3165, 78.0322),
    ("Raipur", "Raipur", "Chhattisgarh", 21.2514, 81.6296),
]

GIVEN_F = ["Meera", "Ananya", "Kavya", "Ishita", "Fatima", "Priya", "Divya", "Sneha",
           "Aarti", "Ritu", "Lakshmi", "Nithya", "Zoya", "Rekha", "Sunita", "Pooja"]
GIVEN_M = ["Arjun", "Devendra", "Rohit", "Imran", "Kartik", "Sanjay", "Vikram", "Aakash",
           "Manoj", "Rahul", "Tejas", "Nikhil", "Farhan", "Suresh", "Anand", "Girish"]
SURNAMES = ["Iyengar", "Nair", "Sheikh", "Kumar", "Deshmukh", "Verma", "Balaji", "Pillai",
            "Chauhan", "Reddy", "Banerjee", "Menon", "Joshi", "Rathore", "Das", "Kulkarni"]

BUILDS = ["Slight", "Slim", "Medium", "Athletic", "Heavy"]
BLOOD = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]
OFFICERS = ["Insp. A. Raghunathan", "SI. K. Deshmukh", "Insp. S. Pillai",
            "Insp. R. Verma", "SI. P. Balaji", "Insp. M. Chauhan"]

MARK_TEMPLATES = [
    ("Scar", "Eyebrow", "{side}", "Linear", "{n} cm horizontal scar above the {side_l} eyebrow"),
    ("Scar", "Hand", "{side}", "Curved", "curved surgical scar across the back of the {side_l} hand"),
    ("Scar", "Knee", "{side}", "Irregular", "old irregular scar on the {side_l} knee"),
    ("Tattoo", "Forearm", "{side}", "Script", "devanagari script tattoo along the inner {side_l} forearm"),
    ("Tattoo", "Shoulder", "{side}", "Pictorial", "faded blue anchor tattoo on the {side_l} shoulder blade"),
    ("Birthmark", "Neck", "Back", "Irregular", "coffee-coloured birthmark at the nape of the neck"),
    ("Birthmark", "Forearm", "{side}", "Oval", "small oval birthmark on the inner {side_l} forearm"),
    ("Other feature", "Ear", "{side}", "Irregular", "partially missing lobe on the {side_l} ear"),
]


def _mark(rng: random.Random, case_id: str) -> Mark:
    kind, location, side_t, shape, text_t = rng.choice(MARK_TEMPLATES)
    side = rng.choice(["Left", "Right"]) if side_t == "{side}" else side_t
    n = rng.choice([1, 1.5, 2, 2.5, 3, 4, 5, 6])
    description = text_t.format(n=n, side=side, side_l=side.lower())
    vector, backend = semantic.embed(description)
    return Mark(
        case_id=case_id, kind=kind, body_location=location, side=side,
        size_text=f"{n:g} cm", size_cm=float(n), shape=shape,
        description=description, embedding=vector,
        embedding_model=backend, extracted_by="manual",
    )


def _random_case(rng: random.Random, index: int, today: date) -> tuple[Case, list[Mark]]:
    case_type = "missing" if rng.random() < 0.78 else "unidentified"
    sex = rng.choice(["Female", "Male"])
    city, district, state, lat, lon = rng.choice(CITIES)

    # jitter coordinates so records are not all stacked on the city centroid
    lat += rng.uniform(-0.35, 0.35)
    lon += rng.uniform(-0.35, 0.35)

    days_ago = int(rng.triangular(3, 2600, 260))
    last_seen = datetime.combine(today - timedelta(days=days_ago), datetime.min.time()) \
        + timedelta(hours=rng.randint(5, 22), minutes=rng.choice([0, 15, 30, 45]))

    age_centre = rng.choice([rng.uniform(4, 17), rng.uniform(18, 35), rng.uniform(36, 72)])
    if rng.random() < 0.45:
        age_mode, half = "range", rng.choice([1.5, 2, 2.5, 3, 4])
        age_lo, age_hi = round(age_centre - half), round(age_centre + half)
    else:
        age_mode, age_lo = "exact", round(age_centre)
        age_hi = age_lo
    if rng.random() < 0.07:
        age_mode, age_lo, age_hi = "unknown", None, None

    if rng.random() < 0.55:
        h_mode = "range"
        base = rng.uniform(120, 185) if (age_lo or 30) > 15 else rng.uniform(95, 155)
        h_lo, h_hi = round(base - rng.choice([2, 3, 4])), round(base + rng.choice([2, 3, 4]))
    elif rng.random() < 0.8:
        h_mode = "exact"
        h_lo = h_hi = round(rng.uniform(120, 185))
    else:
        h_mode, h_lo, h_hi = "unknown", None, None

    name = None
    if case_type == "missing":
        given = rng.choice(GIVEN_F if sex == "Female" else GIVEN_M)
        name = f"{given} {rng.choice(SURNAMES)}"

    case = Case(
        case_number=f"CASE-{last_seen.year}-{5000 + index:04d}",
        case_type=case_type,
        status="UNIDENTIFIED" if case_type == "unidentified" else rng.choice(
            ["ACTIVE", "ACTIVE", "ACTIVE", "UNDER REVIEW"]),
        priority="HIGH PRIORITY" if rng.random() < 0.14 else "ACTIVE",
        name=name, name_known=name is not None,
        age_mode=age_mode, age_lo=age_lo, age_hi=age_hi,
        age_observed_on=last_seen.date() if age_mode != "unknown" else None,
        height_mode=h_mode, height_lo=h_lo, height_hi=h_hi,
        sex=sex if rng.random() > 0.05 else None,
        build=rng.choice(BUILDS) if rng.random() > 0.25 else None,
        blood_type=rng.choice(BLOOD) if rng.random() > 0.62 else None,
        last_seen_at=last_seen,
        location_text=f"{city}, {state}", district=district, state=state,
        lat=round(lat, 4), lon=round(lon, 4),
        circumstances=rng.choice([
            "Did not return from a routine journey. No financial activity since.",
            "Separated from family at a crowded public gathering.",
            "Left residence unaccompanied; not carrying identification.",
            "Found disoriented at a transport terminus, unable to state name or origin.",
            "Admitted to a government hospital after a road traffic incident.",
            "Reported missing by employer after failing to report for duty.",
        ]),
        clothing=rng.choice([
            "Dark kurta, black leggings, canvas sling bag.",
            "Blue work shirt, dark trousers, brown boots.",
            "Cream cotton saree with coloured border, leather chappals.",
            "Printed t-shirt, blue shorts, rubber sandals.",
            "Faded grey shirt, brown trousers, no footwear.",
        ]),
        officer=rng.choice(OFFICERS),
    )

    marks: list[Mark] = []
    for _ in range(rng.choice([0, 1, 1, 1, 2, 2, 3])):
        marks.append(_mark(rng, case.id))
    return case, marks


# ---------------------------------------------------------------------------
def _demo_pair(today: date) -> list[tuple[Case, list[Mark]]]:
    """The planted true match, plus the other cases the UI shows by name."""
    out: list[tuple[Case, list[Mark]]] = []

    def mk(case: Case, specs: list[tuple]) -> None:
        marks = []
        for kind, loc, side, size, shape, text in specs:
            vector, backend = semantic.embed(text)
            marks.append(Mark(
                case_id=case.id, kind=kind, body_location=loc, side=side,
                size_text=size, size_cm=float(size.split()[0]) if size and size[0].isdigit() else None,
                shape=shape, description=text, embedding=vector, embedding_model=backend,
            ))
        out.append((case, marks))

    mk(Case(
        case_number="CASE-2026-0147", case_type="missing", status="ACTIVE",
        priority="HIGH PRIORITY", name="Meera Iyengar", name_known=True,
        age_mode="range", age_lo=23, age_hi=27, age_observed_on=date(2026, 3, 14),
        height_mode="range", height_lo=158, height_hi=164,
        sex="Female", build="Slim", blood_type=None,
        last_seen_at=datetime(2026, 3, 14, 19, 40),
        location_text="Bengaluru, Karnataka", district="Bengaluru Urban", state="Karnataka",
        lat=12.9716, lon=77.5946,
        circumstances=("Did not return from evening commute between Indiranagar and Jayanagar. "
                       "Mobile device last connected to a tower in Domlur at 19:52."),
        clothing="Dark teal kurta, black leggings, tan canvas sling bag, silver anklet on right ankle.",
        officer="Insp. A. Raghunathan",
    ), [
        ("Scar", "Eyebrow", "Left", "3 cm", "Linear", "3 cm horizontal scar above the left eyebrow"),
        ("Birthmark", "Forearm", "Right", "1.5 cm", "Oval", "small oval birthmark on inner right forearm"),
    ])

    mk(Case(
        case_number="CASE-2026-0304", case_type="unidentified", status="UNIDENTIFIED",
        priority="ACTIVE", name=None, name_known=False,
        age_mode="range", age_lo=21, age_hi=26, age_observed_on=date(2026, 8, 3),
        height_mode="range", height_lo=160, height_hi=166,
        sex="Female", build="Slim", blood_type=None,
        last_seen_at=datetime(2026, 8, 3, 22, 30),
        location_text="Chennai, Tamil Nadu", district="Chennai", state="Tamil Nadu",
        lat=13.0827, lon=80.2707,
        circumstances=("Admitted to a government hospital after a road traffic incident; "
                       "unable to provide identity since regaining consciousness."),
        clothing="Dark teal tunic, black trousers, single silver anklet (right).",
        officer="SI. P. Balaji",
    ), [
        ("Scar", "Eyebrow", "Left", "3 cm", "Linear", "small linear scar just over the left eyebrow"),
        ("Birthmark", "Forearm", "Right", "2 cm", "Oval", "faint oval mark on the inside of the right forearm"),
    ])

    # A near-miss: same mark type and site, opposite side. Should be penalised.
    mk(Case(
        case_number="CASE-2026-0271", case_type="unidentified", status="UNIDENTIFIED",
        priority="ACTIVE", name=None, name_known=False,
        age_mode="range", age_lo=22, age_hi=29, age_observed_on=date(2026, 6, 27),
        height_mode="range", height_lo=157, height_hi=165,
        sex="Female", build="Medium", blood_type=None,
        last_seen_at=datetime(2026, 6, 27, 9, 5),
        location_text="Vijayawada, Andhra Pradesh", district="Krishna", state="Andhra Pradesh",
        lat=16.5062, lon=80.6480,
        circumstances="Located at a district shelter; unable to recall personal details.",
        clothing="Green cotton salwar kameez, plastic sandals.",
        officer="SI. K. Deshmukh",
    ), [
        ("Scar", "Eyebrow", "Right", "2 cm", "Linear", "short linear scar above the right eyebrow"),
    ])

    mk(Case(
        case_number="CASE-2026-0231", case_type="missing", status="UNDER REVIEW",
        priority="HIGH PRIORITY", name="Arjun Nair", name_known=True,
        age_mode="exact", age_lo=8, age_hi=8, age_observed_on=date(2019, 8, 11),
        height_mode="range", height_lo=120, height_hi=128,
        sex="Male", build="Slight", blood_type="B+",
        last_seen_at=datetime(2019, 8, 11, 16, 20),
        location_text="Kochi, Kerala", district="Ernakulam", state="Kerala",
        lat=9.9312, lon=76.2673,
        circumstances=("Separated from family at a crowded temple festival. Long-duration case — "
                       "age-progression reasoning applies."),
        clothing="Yellow t-shirt with printed motif, blue shorts, rubber sandals.",
        officer="Insp. S. Pillai",
    ), [
        ("Birthmark", "Neck", "Back", "2 cm", "Irregular", "coffee-coloured birthmark at the nape of the neck"),
    ])

    # The grown-up counterpart of the 2019 child case: exercises age projection.
    mk(Case(
        case_number="CASE-2026-0355", case_type="unidentified", status="UNIDENTIFIED",
        priority="ACTIVE", name=None, name_known=False,
        age_mode="range", age_lo=14, age_hi=17, age_observed_on=date(2026, 5, 20),
        height_mode="range", height_lo=158, height_hi=166,
        sex="Male", build="Slim", blood_type="B+",
        last_seen_at=datetime(2026, 5, 20, 7, 45),
        location_text="Coimbatore, Tamil Nadu", district="Coimbatore", state="Tamil Nadu",
        lat=11.0168, lon=76.9558,
        circumstances="Found working at a roadside establishment; no documents, unclear account of origin.",
        clothing="Oversized checked shirt, worn trousers.",
        officer="SI. P. Balaji",
    ), [
        ("Birthmark", "Neck", "Back", "2 cm", "Irregular", "brown birthmark on the back of the neck"),
    ])

    mk(Case(
        case_number="CASE-2026-0288", case_type="missing", status="ACTIVE",
        priority="HIGH PRIORITY", name="Fatima Sheikh", name_known=True,
        age_mode="exact", age_lo=67, age_hi=67, age_observed_on=date(2026, 7, 22),
        height_mode="range", height_lo=149, height_hi=155,
        sex="Female", build="Slight", blood_type="A+",
        last_seen_at=datetime(2026, 7, 22, 11, 5),
        location_text="Hyderabad, Telangana", district="Hyderabad", state="Telangana",
        lat=17.3850, lon=78.4867,
        circumstances=("Diagnosed with early-stage dementia. Left residence unaccompanied; "
                       "not carrying identification."),
        clothing="Cream cotton saree with maroon border, brown leather chappals, cane walking stick.",
        officer="Insp. R. Verma",
    ), [
        ("Scar", "Hand", "Right", "4 cm", "Curved", "curved surgical scar across the back of the right hand"),
    ])

    mk(Case(
        case_number="CASE-2026-0192", case_type="unidentified", status="UNIDENTIFIED",
        priority="ACTIVE", name=None, name_known=False,
        age_mode="range", age_lo=30, age_hi=38, age_observed_on=date(2026, 5, 2),
        height_mode="exact", height_lo=171, height_hi=171,
        sex="Male", build="Medium", blood_type="O+",
        last_seen_at=datetime(2026, 5, 2, 6, 15),
        location_text="Pune, Maharashtra", district="Pune City", state="Maharashtra",
        lat=18.5204, lon=73.8567,
        circumstances=("Found disoriented at a regional bus terminus, unable to state name or origin. "
                       "Psychiatric evaluation ongoing."),
        clothing="Faded grey shirt, brown trousers, no footwear at time of recovery.",
        officer="SI. K. Deshmukh",
    ), [
        ("Tattoo", "Shoulder", "Left", "6 cm", "Pictorial", "faded blue anchor tattoo on the left shoulder blade"),
    ])

    mk(Case(
        case_number="CASE-2026-0316", case_type="missing", status="ACTIVE",
        priority="ACTIVE", name="Devendra Kumar", name_known=True,
        age_mode="range", age_lo=41, age_hi=45, age_observed_on=date(2026, 6, 18),
        height_mode="exact", height_lo=168, height_hi=168,
        sex="Male", build="Heavy", blood_type=None,
        last_seen_at=datetime(2026, 6, 18, 8, 0),
        location_text="Jaipur, Rajasthan", district="Jaipur", state="Rajasthan",
        lat=26.9124, lon=75.7873,
        circumstances="Reported missing by employer after failing to report for an inter-state assignment.",
        clothing="Blue work shirt with company insignia, dark trousers, brown boots.",
        officer="Insp. M. Chauhan",
    ), [
        ("Tattoo", "Forearm", "Right", "8 cm", "Script", "devanagari script tattoo along the inner right forearm"),
    ])

    return out


# ---------------------------------------------------------------------------
# Cases that depict the same synthetic subject, so the image pipeline has a
# genuine positive to find. Values are (case_number, subject_seed, variant, degradation).
IMAGE_PLAN = [
    ("CASE-2026-0147", 4101, 0, {}),
    ("CASE-2026-0304", 4101, 5, {"blur": 1, "brightness": 0.82, "noise": 0.012}),
    ("CASE-2026-0271", 4207, 0, {"brightness": 0.95}),
    ("CASE-2026-0231", 4310, 0, {}),
    ("CASE-2026-0355", 4310, 6, {"blur": 2, "brightness": 0.78, "noise": 0.02}),
    ("CASE-2026-0288", 4402, 0, {}),
    ("CASE-2026-0192", 4503, 0, {"blur": 1}),
    ("CASE-2026-0316", 4604, 0, {}),
]


def _attach_images(db, by_number: dict[str, Case]) -> int:
    """Attach synthetic portraits and run them through the real image pipeline."""
    from app.config import settings as _settings
    from app.core import quality
    from app.services import face as face_service
    from app.synthetic import write_portrait

    attached = 0
    for case_number, subject, variant, degradation in IMAGE_PLAN:
        case = by_number.get(case_number)
        if case is None or case.images:
            continue
        path = _settings.media_root / case.id / "face.png"
        write_portrait(path, subject, variant, **degradation)

        report = quality.assess(path)
        embedding, model_name, detected = face_service.embed_image(path)
        db.add(Image(
            case_id=case.id, slot="face", path=str(path), mime="image/png",
            width=report.get("width"), height=report.get("height"),
            quality_score=report.get("quality_score"),
            blur_score=report.get("components", {}).get("sharpness"),
            brightness=report.get("raw", {}).get("mean_luminance"),
            resolution_label=report.get("resolution_label"),
            face_visibility=report.get("face_visibility"),
            face_detected=bool(detected or report.get("face_detected")),
            quality_detail=report,
            embedding=embedding, embedding_model=model_name if embedding else None,
        ))
        attached += 1
    return attached


def seed(records: int = 1500, reset: bool = False, seed_value: int = 20260829,
         with_images: bool = True) -> dict:
    init_db()
    rng = random.Random(seed_value)
    today = date(2026, 8, 29)

    with SessionLocal() as db:
        if reset:
            for model in (Candidate, AdaptiveQuestion, MatchRun, Verification, AuditLog, Mark, Image, Case):
                db.execute(delete(model))
            db.commit()

        existing = set(db.scalars(select(Case.case_number)).all())

        created = 0
        for case, marks in _demo_pair(today):
            if case.case_number in existing:
                continue
            db.add(case)
            db.flush()
            for m in marks:
                m.case_id = case.id
                db.add(m)
            created += 1

        for i in range(records):
            case, marks = _random_case(rng, i, today)
            if case.case_number in existing:
                continue
            db.add(case)
            db.flush()
            for m in marks:
                m.case_id = case.id
                db.add(m)
            created += 1
            if created % 250 == 0:
                db.commit()

        db.commit()

        images = 0
        if with_images:
            wanted = [n for n, *_ in IMAGE_PLAN]
            by_number = {
                c.case_number: c
                for c in db.scalars(select(Case).where(Case.case_number.in_(wanted))).all()
            }
            images = _attach_images(db, by_number)
            db.commit()

        total = db.query(Case).count()

    return {"created": created, "total": total, "images": images}


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the CASE//INTEL corpus with fictional data.")
    parser.add_argument("--records", type=int, default=1500, help="synthetic records to add")
    parser.add_argument("--reset", action="store_true", help="delete everything first")
    parser.add_argument("--no-images", action="store_true",
                        help="skip synthetic portraits (the facial stage then has nothing to compare)")
    args = parser.parse_args()

    result = seed(records=args.records, reset=args.reset, with_images=not args.no_images)
    print(f"seeded {result['created']} records ({result['images']} synthetic portraits) "
          f"— {result['total']} total in {engine.url}")
    print("All data is fictional. No real case, person or image is represented.")


if __name__ == "__main__":
    main()
