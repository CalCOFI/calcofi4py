CASE WHEN units = 'count' AND std_haul_factor IS NOT NULL AND tow_type IN ('C1', 'CB', 'CV', 'PV') THEN measurement_value * std_haul_factor / COALESCE(NULLIF(prop_sorted, 0), 1)
     WHEN units IN ('count/m2', 'numberPerMeterSquared') THEN measurement_value * 10
     END AS density_per_10m2,
CASE WHEN units = 'count' AND volume_sampled_m3 IS NOT NULL AND volume_sampled_m3 > 0 THEN measurement_value / COALESCE(NULLIF(prop_sorted, 0), 1) / volume_sampled_m3 * 1000
     WHEN units IN ('count/1000m3') THEN measurement_value
     END AS density_per_1000m3,
CASE WHEN units = 'count' AND std_haul_factor IS NULL AND volume_sampled_m3 IS NULL THEN 'raw_count_no_effort'
     WHEN units = 'count' THEN 'count_with_effort'
     WHEN units IN ('count/m2', 'numberPerMeterSquared', 'count/1000m3') THEN 'density_as_published'
     ELSE 'other_unit' END AS effort_class
