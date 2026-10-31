# Synthetic capture example

`example.json` and `example.csv` describe two fabricated UDP packets, not an
observed network measurement. Regenerate with:

```sh
uv run --locked python scripts/synthetic_capture_example.py
```

The matching payload-free PCAP is generated under ignored `artifacts/`.
Addresses are pseudonyms in the benchmarking range; no actual server addresses,
payloads, credentials or tokens are included. The JSON follows capture schema
version 1.0.0. Counts refer to IPv4 lengths, including IP/transport headers.
