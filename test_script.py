import re
raw_name = "leg.17.stencomm.data20130625.U1.com21.audiz2.audizione.0001.pdf"
DATE_RE = re.compile(r"data(\d{8})")
match = DATE_RE.search(raw_name)
print(match.group(1) if match else "No match")