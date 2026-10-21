"""Date-role extraction for the unstructured IISc tender listing text."""

import re

from pipeline.freshness import parse_date


DATE_PATTERN = re.compile(r"\((\d{1,2}/\d{1,2}/\d{4})\)")
UPDATE_TERMS = re.compile(r"corrigendum|amendment|amended|updated|revised|extension", re.I)
PUBLICATION_TERMS = re.compile(r"published|publication|issued|notice dated", re.I)


def extract_iisc_date_fields(text):
    """Map clearly labeled dates to publication/update fields without guessing.

    Older IISc listings conventionally place the publication date first in
    parentheses. Preserve that convention only when the text does not indicate
    an amendment-only listing. Ambiguous dates remain absent for review.
    """
    matches = list(DATE_PATTERN.finditer(text or ""))
    fields = {"published_date": None, "corrigendum_date": None}
    for index, match in enumerate(matches):
        prefix = (text or "")[max(0, match.start() - 80):match.start()]
        parsed = parse_date(match.group(1))
        if parsed is None:
            continue
        if UPDATE_TERMS.search(prefix):
            fields["corrigendum_date"] = parsed
        elif PUBLICATION_TERMS.search(prefix):
            fields["published_date"] = parsed
        elif index == 0:
            fields["published_date"] = parsed
    return fields
