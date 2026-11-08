"""Sondeo reproducible de concurrencia HTTP, sin dependencias de terceros."""
import argparse
import concurrent.futures
import statistics
import time
import urllib.error
import urllib.request

parser = argparse.ArgumentParser()
parser.add_argument('--url', default='http://127.0.0.1:4000/health')
parser.add_argument('--requests', type=int, default=100)
parser.add_argument('--workers', type=int, default=10)
args = parser.parse_args()

def hit(_):
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(args.url, timeout=10) as response:
            response.read()
            return (time.perf_counter() - start, response.status < 500)
    except (urllib.error.URLError, TimeoutError):
        return (time.perf_counter() - start, False)

started = time.perf_counter()
with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
    results = list(pool.map(hit, range(args.requests)))
duration = time.perf_counter() - started
latencies = sorted(x[0] for x in results)
print(f'url={args.url} requests={args.requests} workers={args.workers} duration_s={duration:.3f}')
print(f'throughput_rps={args.requests/duration:.2f} success={sum(x[1] for x in results)} errors={sum(not x[1] for x in results)}')
print(f'latency_p50_ms={statistics.median(latencies)*1000:.1f} latency_p95_ms={latencies[min(len(latencies)-1, int(len(latencies)*0.95))]*1000:.1f}')
