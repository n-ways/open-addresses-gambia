# How The Gambia addresses places today

This review was carried out in October 2026, before the first issue of home codes. The model's rule is that the Government's own address comes first: where one exists, it is shown as the Government writes it. This document records what exists in The Gambia, with sources, and how the model uses each. The research paper ([`paper.md`](paper.md), section 2) discusses the same systems in the context of international practice.

## 1. The national digital address: Plus Codes

The **National Digital Addressing Policy** (Ministry of Communications and Digital Economy, 2023), prepared with the e-Governance Academy of Estonia, records that the Government has adopted and implemented a digital addressing system based on Plus Codes (the Open Location Code). Every property, home, business, school and health facility is to have one, written as a short code and a town: `F8HC+9G6 Bakau`. The policy gives the Gambia Postal Services Corporation (GAMPOST) responsibility for integrating the national digital addressing system into its procedures and its door-to-door delivery. The Government's Digital Addressing Initiative presents the programme at digitaladdressing.gov.gm.

Kanifing Municipal Council (KMC) implemented Plus Code addressing for about 500,000 residents between July 2021 and February 2022, georeferencing 36,000 properties, and uses it for waste management and property tax collection. The council has linked the codes to its property-rates database, for emergency response and rate collection; it declined to replace them with simpler labels because those would lose accuracy, and it is introducing sequential street numbers as a complement. In January 2023 the Ministry reported 34,464 addresses digitised across Banjul and Kanifing in a 2022 pilot, and 48,770 addresses identified in Kombo North, almost twice the properties in the Brikama Area Council database.

**How the model uses it.** This is the official address of The Gambia, and it covers every point in the country:

- every card shows the Government's Plus Code of the compound's entrance first, with its town, as the official address;
- where a council has numbered a street and the number is known, that street address comes first of all;
- the home code sits beside it as the form that is easy to say and remember (`Bakau 2389`), and leads to the same entrance.

The model issues **no grid of its own**: the spot layer is the Government's Plus Code.

## 2. Postcodes

The Gambia has no postcode system in use. Some international address guides mention a four-digit code; others state that there is none; GAMPOST publishes no postcode list. Addresses are written with the town. The model shows no postcode.

## 3. Street names and house numbers

Banjul has named streets from the colonial period, and Kanifing and some West Coast towns are naming streets. House numbers are rare and are not held in any published register. In OpenStreetMap, 19 compounds carry a street and a number (`addr:street`, `addr:housenumber`); the model shows those first, as written.

## 4. Administrative units used by the model

The Gambia has five regions (West Coast, North Bank, Lower River, Central River, Upper River), the City of Banjul and Kanifing Municipality: seven units, all complete as OpenStreetMap boundary relations. Below them are 8 local government areas and 39 districts. The model's 7 code zones are these seven units, with the abbreviations Gambians already use: BJL, KMC, WCR, NBR, LRR, CRR, URR. Kanifing Municipality has no ISO 3166-2 code of its own.

## 5. Population and buildings

The 2024 Population and Housing Census (Gambia Bureau of Statistics, preliminary report, September 2024) counts 2,422,712 people, 297,581 households, 201,827 compounds and 547,528 buildings or structures, with an annual growth rate of 2.5 % since 2013. The registry holds 672,836 building footprints (OpenStreetMap, and Google and Microsoft footprints conflated by Overture Maps), grouped into 471,030 compounds at the first issue; with the codes issued since, it holds 471,031 codes, each published with its footprints in `registry/`. The registry's compound is a physical unit inferred from footprints and is finer than the census compound: there are 2.33 codes per census compound. The paper (section 6.7) compares the two by local government area.

## Sources

| # | Source | Used for |
|---|---|---|
| 1 | Ministry of Communications and Digital Economy, *National Digital Addressing Policy* (2023), https://mocde.gov.gm/wp-content/uploads/2023/10/Final-National-Digital-Addressing-Policy.pdf | Plus Codes as the national digital address; GAMPOST's role |
| 2 | The Digital Addressing Initiative of The Gambia, https://digitaladdressing.gov.gm/ | the programme and its address form |
| 3 | S. Jobe, "KMC Says Digital Address Codes Will Improve Emergency Response and Property Tax Collection", *Kerr Fatou* (2026), https://www.kerrfatou.com/kmc-says-digital-address-codes-will-improve-emergency-response-and-property-tax-collection/ | KMC's use of the codes, street numbering |
| 4 | L. Badji et al., *Implementing a Comprehensive Digital Addressing System: A Step-by-Step Guide Inspired by the Experience of Kanifing Municipality, The Gambia*, Policy Brief 11 (2025), https://www.ictd.ac/publication/implementing-a-comprehensive-digital-addressing-system-a-step-by-step-guide-inspired-by-the-experience-of-kanifing-municipality-the-gambia/ | the KMC Plus Code programme, 2021-2022 |
| 5 | F. Dem, "Ministry of Digital Economy digitalises 34,464 addresses in Banjul, Kanifing", *The Point* (30 January 2023), https://thepoint.gm/africa/gambia/national-news/ministry-of-digital-ecomomy-digitalises-34-464-addresses-in-banjul-kanifing | addresses digitised in Banjul, Kanifing and Kombo North |
| 6 | Gambia Bureau of Statistics, *Preliminary Report of the 2024 Population and Housing Census in The Gambia* (September 2024), https://gambia.unfpa.org/en/publications/preliminary-report-2024-census-gambia | population, households, compounds and structures by local government area |
| 7 | OpenStreetMap, admin_level=4 relations of The Gambia (© OpenStreetMap contributors, ODbL) | the 7 zone outlines |
| 8 | Wikipedia, *Gambia Postal Services Corporation*, https://en.wikipedia.org/wiki/Gambia_Postal_Services_Corporation | GAMPOST |
