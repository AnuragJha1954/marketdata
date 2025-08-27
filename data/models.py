from django.db import models

class OptionData(models.Model):
    """
    Raw row per (strike, option_type) each time the view runs.
    Keeps the exact values returned by Groww for traceability.
    """
    timestamp = models.DateTimeField(auto_now_add=True)
    symbol = models.CharField(max_length=60)                 # e.g. NIFTY25AUG25000PE
    strike_price = models.IntegerField()
    option_type = models.CharField(max_length=2, choices=[("PE", "Put"), ("CE", "Call")])
    open_interest = models.FloatField(default=0)
    previous_open_interest = models.FloatField(default=0)
    oi_diff = models.FloatField(default=0)                   # open_interest - previous_open_interest

    def __str__(self):
        return f"{self.symbol} @ {self.timestamp:%Y-%m-%d %H:%M:%S}"




class OIDifference(models.Model):
    date = models.DateField(blank=True, null=True)   # Stores only the date (IST at creation time)
    time = models.TimeField(blank=True, null=True)   # Stores only the time (IST at creation time)
    strike = models.IntegerField()
    ce = models.FloatField()
    ce_diff = models.FloatField()
    pe = models.FloatField()
    pe_diff = models.FloatField()

    class Meta:
        ordering = ["-date", "-time"]

    def __str__(self):
        return f"{self.date} {self.time} | Strike {self.strike}"

