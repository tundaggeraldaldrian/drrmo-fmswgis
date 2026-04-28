from whitenoise.storage import CompressedManifestStaticFilesStorage


class RelaxedManifestStaticFilesStorage(CompressedManifestStaticFilesStorage):
    """
    WhiteNoise storage with manifest_strict=False so collectstatic doesn't
    crash when a CSS file references a font that isn't present on disk
    (e.g. Font Awesome's fa-v4compatibility.woff2 which is only in FA Pro).
    """
    manifest_strict = False
