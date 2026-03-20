# Performance Profiling

## Backend — py-spy

Profile live Python processes with zero code changes — no restart needed.

```bash
pip install py-spy
```

```bash
# Attach to running process by PID
py-spy top --pid $(pgrep -f "uvicorn")

# Record a flame graph (30 seconds)
py-spy record -o profile.svg --pid $(pgrep -f "uvicorn") --duration 30

# Sample during load test
py-spy record -o profile.svg --pid $(pgrep -f "uvicorn") --duration 60 --rate 100
# Open profile.svg in browser — wide bars = hotspots
```

### Read flame graphs

```
Wide bar  = function takes a lot of CPU time → optimize this
Tall stack = deep call chain → may indicate recursion or excessive nesting
```

### Profile specific endpoints

```python
# core/profiling.py — enable only in staging
import cProfile, io, pstats
from fastapi import Request

async def profile_middleware(request: Request, call_next):
    if not settings.PROFILING_ENABLED:
        return await call_next(request)

    profiler = cProfile.Profile()
    profiler.enable()
    response = await call_next(request)
    profiler.disable()

    stream = io.StringIO()
    ps = pstats.Stats(profiler, stream=stream).sort_stats("cumulative")
    ps.print_stats(20)  # top 20 functions

    import structlog
    structlog.get_logger().info("profile", path=request.url.path, stats=stream.getvalue())
    return response
```

---

## Backend — Async Profiling

```python
# pip install aiomonitor
# Attach to running async app
import aiomonitor

async def main():
    app = create_app()
    with aiomonitor.start_monitor(loop=asyncio.get_event_loop()):
        # Connect via: nc localhost 50101
        await serve(app)
```

---

## React — Memory Leak Prevention

### Common causes

```tsx
// ❌ Missing cleanup — subscription never removed
useEffect(() => {
  const sub = store.subscribe(handler);
  // forgot: return () => sub.unsubscribe()
}, []);

// ❌ setState after unmount — async operation completes after component gone
useEffect(() => {
  fetchData().then(data => setState(data));  // component may be unmounted
}, []);

// ❌ Event listener never removed
useEffect(() => {
  window.addEventListener('resize', handler);
  // forgot: return () => window.removeEventListener('resize', handler)
}, []);
```

```tsx
// ✅ Always return cleanup function
useEffect(() => {
  const sub = store.subscribe(handler);
  return () => sub.unsubscribe();
}, []);

// ✅ AbortController — cancel fetch on unmount (React Query handles this automatically)
useEffect(() => {
  const controller = new AbortController();
  fetch('/api/data', { signal: controller.signal })
    .then(r => r.json())
    .then(setData)
    .catch(e => { if (e.name !== 'AbortError') throw e; });
  return () => controller.abort();
}, []);

// ✅ Event listener cleanup
useEffect(() => {
  window.addEventListener('resize', handler);
  return () => window.removeEventListener('resize', handler);
}, []);
```

### Detect leaks — React DevTools Profiler

```tsx
// Wrap suspect component in Profiler to measure render time + frequency
import { Profiler } from 'react';

function onRender(id, phase, actualDuration) {
  if (actualDuration > 16) {  // > 16ms = missed a frame
    console.warn(`Slow render: ${id} took ${actualDuration}ms (${phase})`);
  }
}

<Profiler id="UserTable" onRender={onRender}>
  <UserTable />
</Profiler>
```

### Detect leaks — Chrome DevTools

```
1. Open DevTools → Memory tab
2. Take heap snapshot
3. Perform action (navigate away, open/close modal)
4. Take second snapshot
5. Compare snapshots — growing objects = likely leak
6. Look for: detached DOM trees, event listeners, closures holding references
```

---

## React — Render Optimization

```tsx
// ❌ Parent re-renders → all children re-render
function Parent() {
  const [count, setCount] = useState(0);
  return (
    <>
      <button onClick={() => setCount(c => c + 1)}>+</button>
      <ExpensiveChild />  {/* re-renders on every count change — unnecessary */}
    </>
  );
}

// ✅ Memoize expensive children
const ExpensiveChild = React.memo(function ExpensiveChild() {
  // only re-renders if its own props change
  return <div>Expensive</div>;
});

// ✅ Stable callback references
function Parent() {
  const handleClick = useCallback(() => {
    // ...
  }, []);  // stable reference — doesn't cause child re-renders

  return <Child onClick={handleClick} />;
}

// ✅ useMemo for expensive calculations
function Stats({ data }: { data: User[] }) {
  const summary = useMemo(() => {
    return {
      total: data.length,
      active: data.filter(u => u.status === 'active').length,
    };
  }, [data]);  // only recalculates when data changes

  return <div>{summary.active} / {summary.total} active</div>;
}
```

---

## Database Query Profiling

```python
# Find the slowest queries in production
# Run in psql:
SELECT
    query,
    calls,
    total_exec_time / calls AS avg_ms,
    rows / calls AS avg_rows
FROM pg_stat_statements
WHERE calls > 100
ORDER BY avg_ms DESC
LIMIT 20;

# Enable pg_stat_statements in postgresql.conf:
# shared_preload_libraries = 'pg_stat_statements'
# pg_stat_statements.track = all
```

---

## Performance Budget

Set and enforce limits — catch regressions before they reach production.

```javascript
// vite.config.ts
export default {
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ['react', 'react-dom'],
          query: ['@tanstack/react-query'],
        },
      },
    },
    chunkSizeWarningLimit: 200,  // warn if any chunk > 200kb
  },
};
```

```yaml
# .github/workflows/bundle-size.yml
- name: Check bundle size
  run: |
    npm run build
    # Fail if main bundle > 500kb gzipped
    SIZE=$(gzip -c dist/assets/index-*.js | wc -c)
    if [ $SIZE -gt 512000 ]; then
      echo "Bundle too large: ${SIZE} bytes"
      exit 1
    fi
```
