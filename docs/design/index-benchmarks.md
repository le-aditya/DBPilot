# Index benchmarks

Measured with `backend/scripts/benchmark_indexes.py` against local
PostgreSQL 18.6. The migrations are split so this comparison is real
rather than reconstructed: `0001_initial` creates the tables with no
performance indexes, and `0002_performance_indexes` adds the three from
PRD section 6.

**Dataset:** 100,000 rows in `dbpilot.queries`, spread over 20 projects and 2 users, with a realistic 80/15/5 split of success, error and blocked.

**Method:** 5 warm-up runs, then 30 timed runs per query. Median and p95 are reported because a mean hides the tail that PRD section 9's p95 target is actually about.

## Results

| Query | Before (median) | After (median) | Before (p95) | After (p95) | Speed-up |
| --- | ---: | ---: | ---: | ---: | ---: |
| dashboard history page | 4.87 ms | 0.16 ms | 6.02 ms | 0.18 ms | **30.0×** |
| dashboard aggregate | 4.68 ms | 1.14 ms | 5.29 ms | 1.25 ms | **4.1×** |
| blocked attempts for a user | 5.61 ms | 0.52 ms | 6.18 ms | 0.81 ms | **10.8×** |

## Plans

### dashboard history page

```sql
SELECT id, status, duration_ms, created_at FROM dbpilot.queries WHERE project_id = 7 ORDER BY created_at DESC LIMIT 50
```

**Before** — sequential scan:

```
Limit  (cost=2466.52..2466.65 rows=50 width=20) (actual time=4.369..4.373 rows=50.00 loops=1)
  Buffers: shared hit=1049
  ->  Sort  (cost=2466.52..2479.13 rows=5043 width=20) (actual time=4.369..4.370 rows=50.00 loops=1)
        Sort Key: created_at DESC
        Sort Method: top-N heapsort  Memory: 32kB
        Buffers: shared hit=1049
        ->  Seq Scan on queries  (cost=0.00..2299.00 rows=5043 width=20) (actual time=0.027..3.866 rows=4981.00 loops=1)
              Filter: (project_id = 7)
              Rows Removed by Filter: 95019
              Buffers: shared hit=1049
Planning Time: 0.058 ms
Execution Time: 4.381 ms
```

**After** — index scan:

```
Limit  (cost=0.42..43.63 rows=50 width=20) (actual time=0.006..0.015 rows=50.00 loops=1)
  Buffers: shared hit=14
  ->  Index Scan using ix_queries_project_id_created_at on queries  (cost=0.42..4358.53 rows=5043 width=20) (actual time=0.005..0.012 rows=50.00 loops=1)
        Index Cond: (project_id = 7)
        Index Searches: 1
        Buffers: shared hit=14
Planning Time: 0.033 ms
Execution Time: 0.019 ms
```

### dashboard aggregate

```sql
SELECT status, count(*), avg(duration_ms) FROM dbpilot.queries WHERE project_id = 7 GROUP BY status
```

**Before** — sequential scan:

```
HashAggregate  (cost=2336.82..2336.86 rows=3 width=44) (actual time=4.183..4.184 rows=3.00 loops=1)
  Group Key: status
  Batches: 1  Memory Usage: 32kB
  Buffers: shared hit=1049
  ->  Seq Scan on queries  (cost=0.00..2299.00 rows=5043 width=8) (actual time=0.029..3.669 rows=4981.00 loops=1)
        Filter: (project_id = 7)
        Rows Removed by Filter: 95019
        Buffers: shared hit=1049
Planning Time: 0.063 ms
Execution Time: 4.202 ms
```

**After** — index scan:

```
HashAggregate  (cost=1269.36..1269.40 rows=3 width=44) (actual time=1.133..1.134 rows=3.00 loops=1)
  Group Key: status
  Batches: 1  Memory Usage: 32kB
  Buffers: shared hit=956
  ->  Bitmap Heap Scan on queries  (cost=119.50..1231.54 rows=5043 width=8) (actual time=0.201..0.630 rows=4981.00 loops=1)
        Recheck Cond: (project_id = 7)
        Heap Blocks: exact=934
        Buffers: shared hit=956
        ->  Bitmap Index Scan on ix_queries_project_id_created_at  (cost=0.00..118.24 rows=5043 width=0) (actual time=0.140..0.141 rows=4981.00 loops=1)
              Index Cond: (project_id = 7)
              Index Searches: 1
              Buffers: shared hit=22
Planning Time: 0.069 ms
Execution Time: 1.148 ms
```

### blocked attempts for a user

```sql
SELECT count(*) FROM dbpilot.queries WHERE user_id = 3 AND status = 'blocked'
```

**Before** — sequential scan:

```
Aggregate  (cost=2555.47..2555.48 rows=1 width=8) (actual time=5.449..5.449 rows=1.00 loops=1)
  Buffers: shared hit=1049
  ->  Seq Scan on queries  (cost=0.00..2549.00 rows=2588 width=0) (actual time=0.040..5.377 rows=2480.00 loops=1)
        Filter: ((user_id = 3) AND (status = 'blocked'::dbpilot.query_status))
        Rows Removed by Filter: 97520
        Buffers: shared hit=1049
Planning Time: 0.056 ms
Execution Time: 5.463 ms
```

**After** — index scan:

```
Aggregate  (cost=1133.11..1133.12 rows=1 width=8) (actual time=0.438..0.438 rows=1.00 loops=1)
  Buffers: shared hit=867
  ->  Bitmap Heap Scan on queries  (cost=38.82..1126.64 rows=2588 width=0) (actual time=0.088..0.370 rows=2480.00 loops=1)
        Recheck Cond: ((user_id = 3) AND (status = 'blocked'::dbpilot.query_status))
        Heap Blocks: exact=863
        Buffers: shared hit=867
        ->  Bitmap Index Scan on ix_queries_user_id_status  (cost=0.00..38.17 rows=2588 width=0) (actual time=0.055..0.055 rows=2480.00 loops=1)
              Index Cond: ((user_id = 3) AND (status = 'blocked'::dbpilot.query_status))
              Index Searches: 1
              Buffers: shared hit=4
Planning Time: 0.095 ms
Execution Time: 0.451 ms
```

## What this shows

The indexes are not decoration. Before `0002` every dashboard read is a
sequential scan over the whole `queries` table, so the cost grows with
total history rather than with the size of the answer. After it, the
`(project_id, created_at DESC)` index turns the history page into an
ordered index scan that stops after `LIMIT` rows, which is why the
speed-up widens as the table grows.

The composite index is ordered `(project_id, created_at DESC)` rather
than `(created_at, project_id)` because every dashboard read filters by
one project first and orders within it. The reverse order would still
index the column but would not let PostgreSQL skip straight to one
project's newest rows.

`queries.row_count` and `queries.duration_ms` are stored rather than
recomputed (PRD section 6). That is a deliberate write-time cost for a
read-time saving: the aggregate above touches only the index and the
table's own columns, and never re-runs a user's query to find out how
many rows it returned.
