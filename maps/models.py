from django.contrib.gis.db import models
from django.contrib.gis.geos import GEOSGeometry
from django.conf import settings

class Barangay(models.Model):
    id = models.CharField(max_length=9, primary_key=True, verbose_name="ID")
    name = models.CharField(max_length=100, verbose_name="Barangay Name")
    parent_id = models.CharField(max_length=8, verbose_name="Parent ID")
    geometry = models.MultiPolygonField(verbose_name="Boundary")

    def __str__(self):
        return self.name

    @property
    def geojson(self):
        return self.geometry.geojson

class FloodSusceptibility(models.Model):
    lgu = models.CharField(max_length=20, verbose_name="LGU", default="Silay City")
    psgc_lgu = models.CharField(max_length=8, verbose_name="PSGC_LGU", default="64526000")
    haz_class = models.CharField(max_length=20, verbose_name="Hazard Class", default="Flooding")
    haz_code = models.CharField(max_length=3, choices=[
        ('VHF', 'Very High Flood Susceptibility'),
        ('HF', 'High Flood Susceptibility'),
        ('MF', 'Moderate Flood Susceptibility'),
        ('LF', 'Low Flood Susceptibility')
    ], verbose_name="Hazard Code")
    haz_desc = models.CharField(max_length=30, verbose_name="Hazard Description", editable=False)
    haz_area_ha = models.DecimalField(max_digits=15, decimal_places=8, verbose_name="Hazard Area (Ha)")
    geometry = models.MultiPolygonField(verbose_name="Boundary")

    def save(self, *args, **kwargs):
        haz_desc_map = {
            'VHF': 'Very High Flood Susceptibility',
            'HF': 'High Flood Susceptibility',
            'MF': 'Moderate Flood Susceptibility',
            'LF': 'Low Flood Susceptibility'
        }
        self.haz_desc = haz_desc_map.get(self.haz_code, 'Unknown')
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.lgu} - {self.haz_code}"

    @property
    def geojson(self):
        return self.geometry.geojson

# Activity Tracking Models
class AssessmentRecord(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, verbose_name="Staff Member")
    barangay = models.CharField(max_length=100, verbose_name="Barangay")
    latitude = models.DecimalField(max_digits=10, decimal_places=6, verbose_name="Latitude")
    longitude = models.DecimalField(max_digits=10, decimal_places=6, verbose_name="Longitude")
    flood_risk_code = models.CharField(max_length=3, verbose_name="Flood Risk Code")
    flood_risk_description = models.CharField(max_length=100, verbose_name="Flood Risk Description")
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name="Assessment Date/Time")
    is_archived = models.BooleanField(default=False, verbose_name="Archived", db_index=True)
    archived_at = models.DateTimeField(null=True, blank=True, verbose_name="Archived Date/Time")
    
    class Meta:
        ordering = ['-timestamp']
        verbose_name = "Assessment Record"
        verbose_name_plural = "Assessment Records"
        indexes = [
            models.Index(fields=['-timestamp']),
            models.Index(fields=['is_archived', '-timestamp']),
        ]
    
    def __str__(self):
        return f"{self.user.username} - {self.barangay} ({self.timestamp.strftime('%Y-%m-%d %H:%M')})"

class ReportRecord(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, verbose_name="Staff Member")
    assessment = models.ForeignKey(AssessmentRecord, on_delete=models.CASCADE, null=True, blank=True, verbose_name="Related Assessment")
    barangay = models.CharField(max_length=100, verbose_name="Barangay")
    latitude = models.DecimalField(max_digits=10, decimal_places=6, verbose_name="Latitude")
    longitude = models.DecimalField(max_digits=10, decimal_places=6, verbose_name="Longitude")
    flood_risk_code = models.CharField(max_length=3, verbose_name="Flood Risk Code")
    flood_risk_label = models.CharField(max_length=100, verbose_name="Flood Risk Label")
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name="Report Generated Date/Time")
    is_archived = models.BooleanField(default=False, verbose_name="Archived", db_index=True)
    archived_at = models.DateTimeField(null=True, blank=True, verbose_name="Archived Date/Time")
    
    class Meta:
        ordering = ['-timestamp']
        verbose_name = "Report Record"
        verbose_name_plural = "Report Records"
        indexes = [
            models.Index(fields=['-timestamp']),
            models.Index(fields=['is_archived', '-timestamp']),
        ]
    
    def __str__(self):
        return f"{self.user.username} - Report for {self.barangay} ({self.timestamp.strftime('%Y-%m-%d %H:%M')})"

class CertificateRecord(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, verbose_name="Staff Member")
    assessment = models.ForeignKey(AssessmentRecord, on_delete=models.CASCADE, null=True, blank=True, verbose_name="Related Assessment")
    establishment_name = models.CharField(max_length=200, verbose_name="Establishment Name")
    owner_name = models.CharField(max_length=200, verbose_name="Owner Name")
    location = models.TextField(verbose_name="Location")
    barangay = models.CharField(max_length=100, verbose_name="Barangay")
    latitude = models.DecimalField(max_digits=10, decimal_places=6, verbose_name="Latitude")
    longitude = models.DecimalField(max_digits=10, decimal_places=6, verbose_name="Longitude")
    flood_susceptibility = models.CharField(max_length=100, verbose_name="Flood Susceptibility")
    zone_status = models.CharField(max_length=100, verbose_name="Zone Status")
    # NEW: Certification Type and Special Form Fields
    CERTIFICATE_TYPE_CHOICES = [
        ('STANDARD', 'Standard Certificate'),
        ('SPECIAL', 'Special Certification (Restriction)'),
    ]
    certificate_type = models.CharField(max_length=20, choices=CERTIFICATE_TYPE_CHOICES, default='STANDARD', verbose_name="Certificate Type")
    
    purok_name = models.CharField(max_length=200, blank=True, null=True, verbose_name="Purok Name")
    incident_record = models.CharField(max_length=100, blank=True, null=True, verbose_name="Incident Record")
    intended_purpose = models.CharField(max_length=200, blank=True, null=True, verbose_name="Intended Purpose")
    is_suitable = models.BooleanField(default=True, verbose_name="Is Suitable")

    issue_date = models.CharField(max_length=100, verbose_name="Issue Date")
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name="Certificate Generated Date/Time")
    is_archived = models.BooleanField(default=False, verbose_name="Archived", db_index=True)
    archived_at = models.DateTimeField(null=True, blank=True, verbose_name="Archived Date/Time")
    
    class Meta:
        ordering = ['-timestamp']
        verbose_name = "Certificate Record"
        verbose_name_plural = "Certificate Records"
        indexes = [
            models.Index(fields=['-timestamp']),
            models.Index(fields=['is_archived', '-timestamp']),
        ]
    
    def __str__(self):
        return f"{self.user.username} - {self.establishment_name} ({self.timestamp.strftime('%Y-%m-%d %H:%M')})"

# NEW: Flood Record Activity Tracking
class FloodRecordActivity(models.Model):
    ACTION_CHOICES = [
        ('CREATE', 'Created'),
        ('UPDATE', 'Updated'),
        ('DELETE', 'Deleted'),
    ]
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, verbose_name="Staff Member")
    action = models.CharField(max_length=10, choices=ACTION_CHOICES, verbose_name="Action")
    flood_record_id = models.IntegerField(verbose_name="Flood Record ID", null=True, blank=True)
    event_type = models.CharField(max_length=200, verbose_name="Event Type")
    event_date = models.DateTimeField(verbose_name="Event Date")
    affected_barangays = models.CharField(max_length=500, verbose_name="Affected Barangays")
    casualties_dead = models.IntegerField(default=0, verbose_name="Deaths")
    casualties_injured = models.IntegerField(default=0, verbose_name="Injured")
    casualties_missing = models.IntegerField(default=0, verbose_name="Missing")
    affected_persons = models.IntegerField(default=0, verbose_name="Affected Persons")
    affected_families = models.IntegerField(default=0, verbose_name="Affected Families")
    damage_total_php = models.FloatField(default=0, verbose_name="Total Damage (PHP)")
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name="Activity Date/Time")
    is_archived = models.BooleanField(default=False, verbose_name="Archived", db_index=True)
    archived_at = models.DateTimeField(null=True, blank=True, verbose_name="Archived Date/Time")
    
    class Meta:
        ordering = ['-timestamp']
        verbose_name = "Flood Record Activity"
        verbose_name_plural = "Flood Record Activities"
        indexes = [
            models.Index(fields=['-timestamp']),
            models.Index(fields=['is_archived', '-timestamp']),
        ]
    
    def __str__(self):
        return f"{self.user.username} - {self.get_action_display()} flood record for {self.event_type} ({self.timestamp.strftime('%Y-%m-%d %H:%M')})"
    
    @property
    def total_casualties(self):
        return self.casualties_dead + self.casualties_injured + self.casualties_missing