# KDP Publish Packet Generator

Offline, fail-closed generator for **Work Order 05**. It does not authenticate to Amazon, store Amazon credentials, read a `.env`, use a browser, call KDP, schedule itself, or publish content.

## Run

```bash
python3 publishing/kdp_packet_generator.py publishing/titles/example-title/title.json
```

The manifest paths are relative to `title.json`. A complete valid run writes `publishing/packets/{slug}/`. The generator never overwrites a packet.

## Gate behavior

The Merit Gate runs before packet creation. It requires documented comparables and BSRs, a specific differentiation sentence, full verification evidence, five policy clearances, a determined AI disclosure, actual local source assets, seven non-repeated keyword slots, three categories, and evidenced unit economics.

A failed gate writes only `MERIT_GATE.md` with `NO-GO` reasons. It does not create a partial listing, cover, or interior packet.

## Human controls preserved

The output is a preparation artifact only. KDP upload and publication remain human-authorized external actions under the existing title-rights, Founder-approval, and Five Council release gates. The packet itself cannot authorize or carry out publication.
