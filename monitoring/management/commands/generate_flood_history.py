from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import datetime, date
from monitoring.models import FloodRecord
from monitoring.forms import BARANGAYS
import random


class Command(BaseCommand):
    help = 'Generate historical flood records from 2000 to 2025 (1 event per year)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear-existing',
            action='store_true',
            help='Clear existing flood records before generating new data',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING('=' * 70))
        self.stdout.write(self.style.WARNING('GENERATE HISTORICAL FLOOD RECORDS'))
        self.stdout.write(self.style.WARNING('=' * 70))
        self.stdout.write('')
        
        # Clear existing data if requested
        if options['clear_existing']:
            self.stdout.write(self.style.WARNING('Clearing existing flood records...'))
            count = FloodRecord.objects.count()
            FloodRecord.objects.all().delete()
            self.stdout.write(self.style.SUCCESS(f'✓ Cleared {count} existing flood records'))
            self.stdout.write('')
        
        # Event types
        event_types = ['Flood', 'Flash Flood']
        
        # Get all barangay names
        barangay_names = [b[1] for b in BARANGAYS]
        
        # Generate 1 flood per year from 2000 to 2025
        records_created = 0
        
        for year in range(2000, 2026):
            # Random event type
            event_type = random.choice(event_types)
            
            # Random date (prefer rainy season: June-November)
            if random.random() < 0.75:  # 75% chance during rainy season
                month = random.randint(6, 11)
            else:  # 25% chance during other months
                month = random.choice([1, 2, 3, 4, 5, 12])
            
            # Random day based on month
            if month in [1, 3, 5, 7, 8, 10, 12]:
                day = random.randint(1, 31)
            elif month in [4, 6, 9, 11]:
                day = random.randint(1, 30)
            else:  # February
                # Check leap year
                if (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0):
                    day = random.randint(1, 29)
                else:
                    day = random.randint(1, 28)
            
            flood_date = date(year, month, day)
            
            # Random affected barangays (1-5 barangays)
            num_barangays = random.randint(1, 5)
            affected_barangays = random.sample(barangay_names, num_barangays)
            affected_barangays_str = ', '.join(affected_barangays)
            
            # Generate severity (60% moderate, 30% minor, 10% major)
            severity_roll = random.random()
            if severity_roll < 0.10:  # 10% major
                severity = 'major'
            elif severity_roll < 0.40:  # 30% minor
                severity = 'minor'
            else:  # 60% moderate
                severity = 'moderate'
            
            # Generate random values based on severity
            if severity == 'major':
                casualties_dead = random.randint(2, 8)
                casualties_injured = random.randint(20, 50)
                casualties_missing = random.randint(1, 5)
                affected_persons = random.randint(500, 2000)
                affected_families = random.randint(100, 400)
                houses_damaged_partially = random.randint(100, 300)
                houses_damaged_totally = random.randint(20, 80)
                damage_infrastructure_php = random.uniform(5000000, 15000000)
                damage_agriculture_php = random.uniform(2000000, 8000000)
                damage_institutions_php = random.uniform(1000000, 5000000)
                damage_private_commercial_php = random.uniform(3000000, 12000000)
            elif severity == 'minor':
                casualties_dead = 0
                casualties_injured = random.randint(0, 5)
                casualties_missing = 0
                affected_persons = random.randint(50, 200)
                affected_families = random.randint(10, 50)
                houses_damaged_partially = random.randint(5, 30)
                houses_damaged_totally = random.randint(0, 5)
                damage_infrastructure_php = random.uniform(100000, 1000000)
                damage_agriculture_php = random.uniform(50000, 500000)
                damage_institutions_php = random.uniform(50000, 300000)
                damage_private_commercial_php = random.uniform(100000, 800000)
            else:  # moderate
                casualties_dead = random.randint(0, 3)
                casualties_injured = random.randint(5, 25)
                casualties_missing = random.randint(0, 2)
                affected_persons = random.randint(200, 800)
                affected_families = random.randint(50, 150)
                houses_damaged_partially = random.randint(30, 120)
                houses_damaged_totally = random.randint(5, 30)
                damage_infrastructure_php = random.uniform(1000000, 6000000)
                damage_agriculture_php = random.uniform(500000, 3000000)
                damage_institutions_php = random.uniform(300000, 2000000)
                damage_private_commercial_php = random.uniform(800000, 5000000)
            
            # Calculate total damage
            damage_total_php = (
                damage_infrastructure_php +
                damage_agriculture_php +
                damage_institutions_php +
                damage_private_commercial_php
            )
            
            # Create barangay-level breakdown
            barangay_data = self._distribute_to_barangays(
                affected_barangays,
                casualties_dead, casualties_injured, casualties_missing,
                affected_persons, affected_families,
                houses_damaged_partially, houses_damaged_totally,
                damage_infrastructure_php, damage_agriculture_php,
                damage_institutions_php, damage_private_commercial_php
            )
            
            # Create flood record
            flood_record = FloodRecord.objects.create(
                event=event_type,
                date=flood_date,
                affected_barangays=affected_barangays_str,
                barangay_data=barangay_data,
                casualties_dead=casualties_dead,
                casualties_injured=casualties_injured,
                casualties_missing=casualties_missing,
                affected_persons=affected_persons,
                affected_families=affected_families,
                houses_damaged_partially=houses_damaged_partially,
                houses_damaged_totally=houses_damaged_totally,
                damage_infrastructure_php=damage_infrastructure_php,
                damage_agriculture_php=damage_agriculture_php,
                damage_institutions_php=damage_institutions_php,
                damage_private_commercial_php=damage_private_commercial_php,
                damage_total_php=damage_total_php
            )
            
            records_created += 1
            severity_icon = '🔴' if severity == 'major' else '🟡' if severity == 'moderate' else '🟢'
            self.stdout.write(f'{severity_icon} {year}: {event_type} on {flood_date.strftime("%B %d")} - {num_barangays} barangays affected ({severity})')
        
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('=' * 70))
        self.stdout.write(self.style.SUCCESS(f'✓ Successfully generated {records_created} flood records!'))
        self.stdout.write(self.style.SUCCESS('=' * 70))
        self.stdout.write('')
        self.stdout.write('Summary:')
        self.stdout.write(f'  • Years: 2000-2025 (26 years)')
        self.stdout.write(f'  • Records: {records_created} flood events')
        self.stdout.write(f'  • Severity: Mixed (major, moderate, minor)')

    def _distribute_to_barangays(self, barangays, casualties_dead, casualties_injured, 
                                   casualties_missing, affected_persons, affected_families,
                                   houses_damaged_partially, houses_damaged_totally,
                                   damage_infrastructure_php, damage_agriculture_php,
                                   damage_institutions_php, damage_private_commercial_php):
        """Distribute totals across affected barangays"""
        barangay_data = {
            'casualties_dead': {},
            'casualties_injured': {},
            'casualties_missing': {},
            'affected_persons': {},
            'affected_families': {},
            'houses_damaged_partially': {},
            'houses_damaged_totally': {},
            'damage_infrastructure_php': {},
            'damage_agriculture_php': {},
            'damage_institutions_php': {},
            'damage_private_commercial_php': {}
        }
        
        num_barangays = len(barangays)
        
        # Distribute values with random weights
        weights = [random.random() for _ in range(num_barangays)]
        weight_sum = sum(weights)
        normalized_weights = [w / weight_sum for w in weights]
        
        for i, barangay in enumerate(barangays):
            weight = normalized_weights[i]
            
            # Distribute integers
            if casualties_dead > 0:
                value = max(0, int(casualties_dead * weight))
                if value > 0:
                    barangay_data['casualties_dead'][barangay] = value
            
            if casualties_injured > 0:
                value = max(0, int(casualties_injured * weight))
                if value > 0:
                    barangay_data['casualties_injured'][barangay] = value
            
            if casualties_missing > 0:
                value = max(0, int(casualties_missing * weight))
                if value > 0:
                    barangay_data['casualties_missing'][barangay] = value
            
            value = max(0, int(affected_persons * weight))
            if value > 0:
                barangay_data['affected_persons'][barangay] = value
            
            value = max(0, int(affected_families * weight))
            if value > 0:
                barangay_data['affected_families'][barangay] = value
            
            value = max(0, int(houses_damaged_partially * weight))
            if value > 0:
                barangay_data['houses_damaged_partially'][barangay] = value
            
            value = max(0, int(houses_damaged_totally * weight))
            if value > 0:
                barangay_data['houses_damaged_totally'][barangay] = value
            
            # Distribute financial values (floats)
            value = round(damage_infrastructure_php * weight, 2)
            if value > 0:
                barangay_data['damage_infrastructure_php'][barangay] = value
            
            value = round(damage_agriculture_php * weight, 2)
            if value > 0:
                barangay_data['damage_agriculture_php'][barangay] = value
            
            value = round(damage_institutions_php * weight, 2)
            if value > 0:
                barangay_data['damage_institutions_php'][barangay] = value
            
            value = round(damage_private_commercial_php * weight, 2)
            if value > 0:
                barangay_data['damage_private_commercial_php'][barangay] = value
        
        return barangay_data
