# Methodology Notes

## Current prototype status

This is not yet a national forecast. It is a prototype that displays approved polling records and simple scenario stress tests.

## Current model limitations

- Polling data coverage is still thin.
- Pollster house effects are not yet estimated.
- No full weighted polling average is implemented yet.
- Constituency and MP-seat simulations require official constituency baselines before they should be used seriously.
- Scenario outputs use simplified uncertainty assumptions and should not be treated as predictions.

## Future national-grade methodology

The next phases should add:

- pollster quality scoring;
- recency and sample-size weighted averages;
- confidence intervals or credible intervals;
- county-level presidential threshold modeling;
- historical IEBC election baselines;
- constituency-level swing and seat models;
- model versioning and audit logs.

## Interpretation standard

Every chart should answer:

1. Where did the number come from?
2. What exactly was measured?
3. How comparable is it to other records?
4. How uncertain is it?
5. What assumptions drive the scenario result?
