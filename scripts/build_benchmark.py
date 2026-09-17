"""Build explicit synthetic stress cases and DOI-derived weak labels; never manual truth."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def split(group):
    bucket = int(hashlib.sha256(group.encode()).hexdigest()[:8], 16) % 10
    return "development" if bucket < 6 else "validation" if bucket < 8 else "test"


def build():
    records, pairs = [], []
    topics = [
        "Quantum interference in coupled resonators",
        "Neutrino mixing in dense matter",
        "Lattice simulation of gauge fields",
        "Optical cooling of trapped atoms",
        "Dark matter detection with liquid xenon",
        "Gravitational waves from binary stars",
        "Superconductivity in layered materials",
        "Cosmic ray propagation in the galaxy",
        "Thermal transport in nanostructures",
        "Plasma confinement in magnetic fields",
        "Black hole evaporation and entropy",
        "Muon scattering in thin targets",
        "Photon entanglement in optical fibres",
        "Nuclear structure of exotic isotopes",
        "Electron transport in graphene devices",
        "Higgs boson decay measurements",
        "Stellar evolution in low metallicity environments",
        "Magnetic ordering of spin chains",
        "Vacuum fluctuations in confined geometries",
        "Particle acceleration in shock waves",
        "Axion searches in resonant cavities",
        "Radiation damage in silicon detectors",
        "Precision spectroscopy of hydrogen",
        "Turbulent mixing in relativistic jets",
        "Heavy ion collisions at high energy",
        "Quark confinement at finite temperature",
        "Quantum computing with trapped ions",
        "Topological phases in condensed matter",
        "Solar neutrino flux measurements",
        "Cosmological expansion from standard candles",
    ]
    for i, title in enumerate(topics):
        family = f"synthetic-family-{i:02}"
        base = {
            "title": title,
            "DOI": f"10.99999/srr.synthetic.{i}",
            "type": "journal-article",
            "author": [{"given": "Synthetic", "family": f"Author{i}"}],
            "published-print": {"date-parts": [[2020 + i % 4]]},
        }
        variants = {
            "base": base,
            "same": {**base, "title": "  " + title.upper() + "  "},
            "missing": {**base, "DOI": "", "title": title},
            "negative": {
                **base,
                "DOI": f"10.99999/srr.synthetic.{i}.other",
                "title": title + " without equilibrium",
            },
            "preprint": {
                **base,
                "DOI": f"10.99999/srr.synthetic.{i}.preprint",
                "type": "posted-content",
            },
            "ambiguous": {"title": title, "type": "journal-article"},
        }
        for name, raw in variants.items():
            records.append(
                {
                    "id": f"{family}:{name}",
                    "group": family,
                    "split": split(family),
                    "origin": "synthetic",
                    "provider": "crossref",
                    "raw": raw,
                }
            )
        for name, label, reason in [
            ("same", "same", "Constructed case/whitespace variant of the same invented edition."),
            ("missing", "same", "Constructed DOI omission; identity known only from generation."),
            (
                "negative",
                "different",
                "Invented distinct publication with negation and distinct identifier.",
            ),
            (
                "preprint",
                "different",
                "Different invented edition; preprint is not the journal edition.",
            ),
            ("ambiguous", "ambiguous", "Title alone cannot establish identity."),
        ]:
            pairs.append(
                {
                    "left": f"{family}:base",
                    "right": f"{family}:{name}",
                    "label": label,
                    "label_source": "synthetic",
                    "reason": reason,
                }
            )
    real_path = ROOT / "data/demo.json"
    if real_path.exists():
        from records.normalization import normalize_record

        grouped = {}
        for n, item in enumerate(json.loads(real_path.read_text())):
            if item.get("provider") not in ("crossref", "openalex"):
                continue
            raw = item.get("raw", {})
            doi = normalize_record(item["provider"], raw)["doi"]
            if not doi or "99999" in doi:
                continue
            group = "real-doi:" + doi
            rec = {
                "id": f"real:{item['provider']}:{n}",
                "group": group,
                "split": split(group),
                "origin": "real",
                "provider": item["provider"],
                "raw": raw,
            }
            records.append(rec)
            grouped.setdefault(group, []).append(rec)
        for group, members in grouped.items():
            for a in members:
                for b in members:
                    if a["provider"] == "crossref" and b["provider"] == "openalex":
                        pairs.append(
                            {
                                "left": a["id"],
                                "right": b["id"],
                                "label": "same",
                                "label_source": "weak_identifier",
                                "reason": "Equal normalized DOI; not independent human verification.",
                            }
                        )
    return {
        "schema_version": 1,
        "split_policy": "SHA256 publication family, 60/20/20 expected (actual counts reported)",
        "annotation_status": "No human or expert annotations; synthetic stress and DOI weak labels only.",
        "records": records,
        "pairs": pairs,
    }


if __name__ == "__main__":
    import sys

    sys.path.insert(0, str(ROOT))
    destination = ROOT / "data/benchmark.json"
    destination.write_text(json.dumps(build(), ensure_ascii=False, indent=2) + "\n")
    print(destination)
