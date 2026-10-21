# Demo icon attribution — V7.1

The V7.1 demo seeder uses the Game-icons.net white-on-transparent PNG archive and transforms selected icons into small Lost Kingsland WebP UI/emote placeholders.

License: CC BY 3.0 (some source icons may additionally be public domain). If these placeholders remain in a public build, retain attribution to Game-icons.net and the individual authors recorded by the site/archive.

Core asset preferences:
- GOLD — `shiny-purse` — Lorc
- GEMS — `gems` — Lorc
- WOOD — `log` — Delapouite
- ORE — `ore` — Faithtoken
- FOOD — `wheat` — Lorc
- ESSENCE — `concentration-orb` — Lorc
- CULTIVATION_QI — `aura` — Lorc
- SKILL_POINT — `upgrade` — Delapouite
- CLAN_MARKS — `shield` — sbed
- SEASON_TOKEN — `token` — Delapouite

For the 80 equipment ores, the seeder chooses ore/mineral and target-slot silhouettes from the same archive, records the actual chosen source filenames in each media asset's PostgreSQL `metadata`, and stores the transformed WebP bytes in shared media.

Source: https://game-icons.net/
