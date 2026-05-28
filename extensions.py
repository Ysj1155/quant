# extensions.py
try:
    from flask_caching import Cache
except ModuleNotFoundError:
    class Cache:
        def init_app(self, app, config=None):
            return None

        def cached(self, *args, **kwargs):
            def decorator(func):
                return func
            return decorator

        def memoize(self, *args, **kwargs):
            def decorator(func):
                return func
            return decorator

        def clear(self):
            return None

        def delete_memoized(self, *args, **kwargs):
            return None


cache = Cache()
