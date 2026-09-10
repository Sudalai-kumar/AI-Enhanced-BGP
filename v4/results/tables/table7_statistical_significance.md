| Scenario   | Comparison   | Variant 1 MTTM   | Variant 2 MTTM   | t-statistic   | p-value   | Significant?   |
|:-----------|:-------------|:-----------------|:-----------------|:--------------|:----------|:---------------|
| S2         | A2 vs A3     | 0.1 s            | 0.1 s            | nan           | nan       | No             |
| S2         | A3 vs A4     | 0.1 s            | 0.1 s            | nan           | nan       | No             |
| S2         | A2 vs A4     | 0.1 s            | 0.1 s            | nan           | nan       | No             |
| S2         | A1 vs A4     | 0.1 s            | 0.1 s            | nan           | nan       | No             |
| S3         | A2 vs A3     | N/A              | 0.362 s          | N/A           | N/A       | No             |
| S3         | A3 vs A4     | 0.362 s          | 0.94 s           | -3.6524       | 0.001998  | Yes (p < 0.05) |
| S3         | A2 vs A4     | N/A              | 0.94 s           | N/A           | N/A       | No             |
| S3         | A1 vs A4     | 0.1 s            | 0.94 s           | -6.6804       | 9.1e-05   | Yes (p < 0.05) |
| S6         | A2 vs A3     | N/A              | 0.1 s            | N/A           | N/A       | No             |
| S6         | A3 vs A4     | 0.1 s            | 0.463 s          | -12.3054      | 1e-06     | Yes (p < 0.05) |
| S6         | A2 vs A4     | N/A              | 0.463 s          | N/A           | N/A       | No             |
| S6         | A1 vs A4     | 0.1 s            | 0.463 s          | -12.3054      | 1e-06     | Yes (p < 0.05) |