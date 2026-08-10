"""
Custom static-files storage backend.

Django's ManifestStaticFilesStorage (which WhiteNoise's
CompressedManifestStaticFilesStorage extends) crashes `collectstatic` if any
CSS file references an asset it can't find on disk - this happens with some
versions of Django's own admin CSS (e.g. referencing admin/img/sorting-icons.svg)
depending on exactly which admin static files get bundled. Setting
`manifest_strict = False` makes it skip those references gracefully instead of
failing the whole deploy, which is what the WHITENOISE_MANIFEST_STRICT setting
is *supposed* to do but doesn't reliably affect the collectstatic build step -
overriding the class attribute directly is the guaranteed fix.
"""
from whitenoise.storage import CompressedManifestStaticFilesStorage


class NonStrictManifestStaticFilesStorage(CompressedManifestStaticFilesStorage):
    manifest_strict = False
