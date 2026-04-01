"""
Output manager (Lightroom-safe): writes metadata outputs only.

This module must never move, rename, or reorganize original files on disk.
"""

import os
from xml.etree import ElementTree as ET

from typing import Iterable, List, Optional, Tuple


def ensure_output_dirs(base_output_dir: str) -> Tuple[str, str, str]:
    """
    Ensure the output folder structure exists.

    Returns:
        (metadata_csv_path, suggested_keywords_csv_path, optional_xmp_dir)
    """
    os.makedirs(base_output_dir, exist_ok=True)
    metadata_csv_path = os.path.join(base_output_dir, "metadata.csv")
    suggested_keywords_csv_path = os.path.join(base_output_dir, "suggested_keywords.csv")
    optional_xmp_dir = os.path.join(base_output_dir, "optional_xmp")
    os.makedirs(optional_xmp_dir, exist_ok=True)
    return metadata_csv_path, suggested_keywords_csv_path, optional_xmp_dir


def xmp_sidecar_path_for_image(original_image_path: str) -> str:
    """
    Return the Lightroom-compatible XMP sidecar path next to the original image.

    Example: 14007.jpg -> 14007.xmp (same directory).
    """
    return os.path.splitext(original_image_path)[0] + ".xmp"


def _clean_keywords(words: Iterable[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for w in words:
        kw = (w or "").strip()
        if not kw:
            continue
        norm = kw.lower()
        if norm in seen:
            continue
        seen.add(norm)
        out.append(kw)
    return out


def write_xmp_sidecar(
    xmp_path: str,
    *,
    keywords: List[str],
    hierarchical_keywords: Optional[List[str]] = None,
) -> None:
    """
    Write an Adobe Lightroom Classic compatible XMP sidecar file.

    - Does not modify the original image file
    - Writes UTF-8 XML with RDF structure
    - Stores keywords in both:
        - dc:subject (Bag of rdf:li) (Lightroom reads this)
        - photoshop:Keywords (comma-separated string) (useful for compatibility)
    - Optionally stores lr:hierarchicalSubject (Bag of rdf:li)
    """
    keywords = _clean_keywords(keywords)
    hierarchical_keywords = _clean_keywords(hierarchical_keywords or [])

    # Namespaces
    ns = {
        "x": "adobe:ns:meta/",
        "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
        "dc": "http://purl.org/dc/elements/1.1/",
        "xmp": "http://ns.adobe.com/xap/1.0/",
        "photoshop": "http://ns.adobe.com/photoshop/1.0/",
        "lr": "http://ns.adobe.com/lightroom/1.0/",
    }
    for prefix, uri in ns.items():
        ET.register_namespace(prefix, uri)

    xmpmeta = ET.Element(ET.QName(ns["x"], "xmpmeta"))
    rdf = ET.SubElement(xmpmeta, ET.QName(ns["rdf"], "RDF"))
    desc = ET.SubElement(rdf, ET.QName(ns["rdf"], "Description"), {ET.QName(ns["rdf"], "about"): ""})

    # dc:subject -> rdf:Bag of rdf:li
    dc_subject = ET.SubElement(desc, ET.QName(ns["dc"], "subject"))
    bag = ET.SubElement(dc_subject, ET.QName(ns["rdf"], "Bag"))
    for kw in keywords:
        li = ET.SubElement(bag, ET.QName(ns["rdf"], "li"))
        li.text = kw

    # photoshop:Keywords (comma-separated)
    ps_keywords = ET.SubElement(desc, ET.QName(ns["photoshop"], "Keywords"))
    ps_keywords.text = ", ".join(keywords)

    # lr:hierarchicalSubject -> rdf:Bag of rdf:li
    if hierarchical_keywords:
        lr_h = ET.SubElement(desc, ET.QName(ns["lr"], "hierarchicalSubject"))
        hbag = ET.SubElement(lr_h, ET.QName(ns["rdf"], "Bag"))
        for hkw in hierarchical_keywords:
            li = ET.SubElement(hbag, ET.QName(ns["rdf"], "li"))
            li.text = hkw

    xml_bytes = ET.tostring(xmpmeta, encoding="utf-8", xml_declaration=True)
    os.makedirs(os.path.dirname(xmp_path) or ".", exist_ok=True)
    with open(xmp_path, "wb") as f:
        f.write(xml_bytes)
