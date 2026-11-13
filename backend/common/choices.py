"""Business lookup lists. The frontend reads these from /api/meta/options/ instead of hard-coding them."""

NEEDS = ["Finished Leather", "Raw Leather", "Leather Sheets", "Leather Rolls", "Custom"]
LEATHER_TYPES = ["Cow", "Buffalo", "Goat", "Sheep", "Calf", "Other"]
APPLICATIONS = ["Footwear", "Bags", "Furniture", "Automotive", "Garments", "Accessories", "Other"]
FINISHES = ["Full Grain", "Top Grain", "Corrected Grain", "Suede", "Nubuck", "Patent", "Aniline", "Semi-Aniline"]
COLORS = {
    "Black": "#1C1612", "Brown": "#6B4429", "Tan": "#B98A56", "White": "#EDE6D8",
    "Red": "#8E2F26", "Blue": "#2D4561", "Green": "#3C5A3E", "Custom": "#9A8B7A",
}
UNITS = [("SQ_FT", "sq ft"), ("SQ_M", "sq m"), ("KG", "kg"), ("PIECES", "pieces")]
THICKNESS_BANDS = [
    {"label": "0.6–0.9 mm", "min": "0.6", "max": "0.9"},
    {"label": "1.0–1.4 mm", "min": "1.0", "max": "1.4"},
    {"label": "1.5–2.0 mm", "min": "1.5", "max": "2.0"},
    {"label": "2.0+ mm", "min": "2.0", "max": "6.0"},
]
CERTIFICATIONS = ["LWG Gold", "LWG Silver", "LWG Bronze", "ISO 9001", "ISO 14001", "REACH", "IATF 16949"]
DOCUMENT_KINDS = ["CERTIFICATE", "SAMPLE", "OTHER"]
ORDER_DOCUMENT_KINDS = ["QC_REPORT", "PACKING_LIST", "INVOICE", "OTHER"]


def unit_label(code):
    return dict(UNITS).get(code, code)
