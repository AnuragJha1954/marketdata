from django.contrib import admin
from .models import OptionData, OIDifference

@admin.register(OptionData)
class OptionDataAdmin(admin.ModelAdmin):
    list_display = ("timestamp", "symbol", "strike_price", "option_type", "open_interest", "previous_open_interest", "oi_diff")
    list_filter = ("option_type", "strike_price", "timestamp")
    search_fields = ("symbol",)

@admin.register(OIDifference)
class OIDifferenceAdmin(admin.ModelAdmin):
    list_display = ("time","date", "strike", "ce", "ce_diff", "pe", "pe_diff")
    list_filter = ("time","date","strike")
    search_fields = ("strike",)