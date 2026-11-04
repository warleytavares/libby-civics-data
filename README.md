# Libby Civics data

`officials.json` holds the names that change on the U.S. naturalization civics test (President, Vice President, Speaker, Chief Justice, governors, senators, representatives and delegates).
It is rebuilt every day by `.github/workflows/update-officials.yml` using `update_officials.py` (Congress data from unitedstates/congress-legislators, governors and federal officeholders from Wikipedia). If a sanity check fails the file is not overwritten.

The official answer list is always the one at https://www.uscis.gov/citizenship/testupdates.
