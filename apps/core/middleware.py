class HolidaySyncMiddleware:
    """Dispara en segundo plano la actualización semanal de feriados (ver apps.licencias.sync)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith(("/static/", "/estado/")):
            return response
        from apps.licencias.sync import maybe_sync_in_background

        maybe_sync_in_background()
        return response
