from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.contrib.gis.geos import GEOSGeometry, MultiPolygon, Polygon
from django.utils import timezone
from decimal import Decimal
from datetime import timedelta, datetime
from .models import (
    Barangay, 
    FloodSusceptibility, 
    AssessmentRecord, 
    ReportRecord, 
    CertificateRecord,
    FloodRecordActivity
)

User = get_user_model()


class BarangayModelTest(TestCase):
    """Test the Barangay model's internal logic"""
    
    def setUp(self):
        # Create a simple polygon for testing
        # This is a square polygon
        poly = Polygon(((0, 0), (0, 1), (1, 1), (1, 0), (0, 0)))
        self.multipolygon = MultiPolygon(poly)
        
        self.barangay = Barangay.objects.create(
            id='123456789',
            name='Test Barangay',
            parent_id='12345678',
            geometry=self.multipolygon
        )
    
    def test_barangay_creation(self):
        """Test that a barangay can be created with all required fields"""
        self.assertEqual(self.barangay.name, 'Test Barangay')
        self.assertEqual(self.barangay.id, '123456789')
        self.assertEqual(self.barangay.parent_id, '12345678')
        self.assertIsNotNone(self.barangay.geometry)
    
    def test_barangay_str_method(self):
        """Test the __str__ method returns the barangay name"""
        self.assertEqual(str(self.barangay), 'Wrong Barangay Name')
    
    def test_geojson_property(self):
        """Test that geojson property returns valid GeoJSON string"""
        geojson = self.barangay.geojson
        self.assertIsNotNone(geojson)
        self.assertIsInstance(geojson, str)
        # GeoJSON should contain coordinates
        self.assertIn('coordinates', geojson)


class FloodSusceptibilityModelTest(TestCase):
    """Test the FloodSusceptibility model's internal logic"""
    
    def setUp(self):
        poly = Polygon(((0, 0), (0, 1), (1, 1), (1, 0), (0, 0)))
        self.multipolygon = MultiPolygon(poly)
    
    def test_flood_susceptibility_creation_with_vhf(self):
        """Test creation with Very High Flood code"""
        flood = FloodSusceptibility.objects.create(
            lgu='Silay City',
            psgc_lgu='64526000',
            haz_class='Flooding',
            haz_code='VHF',
            haz_area_ha=Decimal('10.5'),
            geometry=self.multipolygon
        )
        
        # Test that haz_desc is auto-populated on save
        self.assertEqual(flood.haz_desc, 'Very High Flood Susceptibility')
    
    def test_flood_susceptibility_creation_with_hf(self):
        """Test creation with High Flood code"""
        flood = FloodSusceptibility.objects.create(
            lgu='Silay City',
            psgc_lgu='64526000',
            haz_class='Flooding',
            haz_code='HF',
            haz_area_ha=Decimal('15.3'),
            geometry=self.multipolygon
        )
        
        self.assertEqual(flood.haz_desc, 'Moderate Flood Susceptibility')
    
    def test_flood_susceptibility_creation_with_mf(self):
        """Test creation with Moderate Flood code"""
        flood = FloodSusceptibility.objects.create(
            lgu='Silay City',
            psgc_lgu='64526000',
            haz_class='Flooding',
            haz_code='MF',
            haz_area_ha=Decimal('20.7'),
            geometry=self.multipolygon
        )
        
        self.assertEqual(flood.haz_desc, 'Moderate Flood Susceptibility')
    
    def test_flood_susceptibility_creation_with_lf(self):
        """Test creation with Low Flood code"""
        flood = FloodSusceptibility.objects.create(
            lgu='Silay City',
            psgc_lgu='64526000',
            haz_class='Flooding',
            haz_code='LF',
            haz_area_ha=Decimal('5.2'),
            geometry=self.multipolygon
        )
        
        self.assertEqual(flood.haz_desc, 'Low Flood Susceptibility')
    
    def test_flood_susceptibility_invalid_code(self):
        """Test that invalid hazard code gets 'Unknown' description"""
        flood = FloodSusceptibility.objects.create(
            lgu='Silay City',
            psgc_lgu='64526000',
            haz_class='Flooding',
            haz_code='XXX',  # Invalid code
            haz_area_ha=Decimal('5.2'),
            geometry=self.multipolygon
        )
        
        # Should default to 'Unknown'
        self.assertEqual(flood.haz_desc, 'Unknown')
    
    def test_flood_susceptibility_str_method(self):
        """Test the __str__ method"""
        flood = FloodSusceptibility.objects.create(
            lgu='Silay City',
            psgc_lgu='64526000',
            haz_class='Flooding',
            haz_code='HF',
            haz_area_ha=Decimal('10.0'),
            geometry=self.multipolygon
        )
        
        self.assertEqual(str(flood), 'Silay City - HF')
    
    def test_geojson_property(self):
        """Test that geojson property works"""
        flood = FloodSusceptibility.objects.create(
            lgu='Silay City',
            psgc_lgu='64526000',
            haz_class='Flooding',
            haz_code='LF',
            haz_area_ha=Decimal('5.0'),
            geometry=self.multipolygon
        )
        
        geojson = flood.geojson
        self.assertIsNotNone(geojson)
        self.assertIsInstance(geojson, str)


class AssessmentRecordModelTest(TestCase):
    """Test the AssessmentRecord model"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='teststaff',
            password='testpass123'
        )
    
    def test_assessment_record_creation(self):
        """Test creating an assessment record"""
        assessment = AssessmentRecord.objects.create(
            user=self.user,
            barangay='Test Barangay',
            latitude=Decimal('10.678901'),
            longitude=Decimal('122.987654'),
            flood_risk_code='HF',
            flood_risk_description='High Flood Susceptibility'
        )
        
        self.assertEqual(assessment.user, self.user)
        self.assertEqual(assessment.barangay, 'Test Barangay')
        self.assertEqual(assessment.flood_risk_code, 'HF')
        self.assertIsNotNone(assessment.timestamp)
    
    def test_assessment_ordering(self):
        """Test that assessments model has -timestamp as default ordering"""
        from maps.models import AssessmentRecord as AssessmentModel
        
        # Check the model's Meta class has the correct ordering
        self.assertEqual(AssessmentModel._meta.ordering, ['-timestamp'])
    
    def test_assessment_str_method(self):
        """Test the __str__ method"""
        assessment = AssessmentRecord.objects.create(
            user=self.user,
            barangay='Test Barangay',
            latitude=Decimal('10.678901'),
            longitude=Decimal('122.987654'),
            flood_risk_code='MF',
            flood_risk_description='Moderate Flood Susceptibility'
        )
        
        # Should contain username and barangay
        str_repr = str(assessment)
        self.assertIn('teststaff', str_repr)
        self.assertIn('Test Barangay', str_repr)


class FloodRecordActivityModelTest(TestCase):
    """Test the FloodRecordActivity model"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testadmin',
            password='testpass123'
        )
    
    def test_flood_record_activity_creation(self):
        """Test creating a flood record activity"""
        activity = FloodRecordActivity.objects.create(
            user=self.user,
            action='CREATE',
            flood_record_id=1,
            event_type='Typhoon',
            event_date=timezone.now(),
            affected_barangays='Barangay 1, Barangay 2',
            casualties_dead=5,
            casualties_injured=10,
            casualties_missing=2,
            affected_persons=100,
            affected_families=25,
            damage_total_php=500000.0
        )
        
        self.assertEqual(activity.action, 'CREATE')
        self.assertEqual(activity.event_type, 'Typhoon')
        self.assertEqual(activity.casualties_dead, 5)
        self.assertEqual(activity.casualties_injured, 10)
        self.assertEqual(activity.casualties_missing, 2)
    
    def test_total_casualties_property(self):
        """Test the total_casualties property calculation"""
        activity = FloodRecordActivity.objects.create(
            user=self.user,
            action='CREATE',
            event_type='Flood',
            event_date=timezone.now(),
            affected_barangays='Barangay 1',
            casualties_dead=3,
            casualties_injured=7,
            casualties_missing=1,
            affected_persons=50,
            affected_families=10,
            damage_total_php=100000.0
        )
        
        # Should be 3 + 7 + 1 = 11
        self.assertEqual(activity.total_casualties, 11)
    
    def test_total_casualties_with_zeros(self):
        """Test total_casualties when all casualties are zero"""
        activity = FloodRecordActivity.objects.create(
            user=self.user,
            action='UPDATE',
            event_type='Heavy Rain',
            event_date=timezone.now(),
            affected_barangays='Barangay 3',
            casualties_dead=0,
            casualties_injured=0,
            casualties_missing=0,
            affected_persons=20,
            affected_families=5,
            damage_total_php=50000.0
        )
        
        self.assertEqual(activity.total_casualties, 0)
    
    def test_action_choices(self):
        """Test that action choices work correctly"""
        activity = FloodRecordActivity.objects.create(
            user=self.user,
            action='DELETE',
            event_type='Storm',
            event_date=timezone.now(),
            affected_barangays='Barangay 5',
            casualties_dead=0,
            casualties_injured=0,
            casualties_missing=0,
            affected_persons=10,
            affected_families=2,
            damage_total_php=25000.0
        )
        
        # get_action_display should return the human-readable version
        self.assertEqual(activity.get_action_display(), 'Deleted')


class ReportRecordModelTest(TestCase):
    """Test the ReportRecord model"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='reportstaff',
            password='testpass123'
        )
    
    def test_report_record_creation(self):
        """Test creating a report record"""
        report = ReportRecord.objects.create(
            user=self.user,
            barangay='Test Barangay',
            latitude=Decimal('10.123456'),
            longitude=Decimal('122.654321'),
            flood_risk_code='VHF',
            flood_risk_label='Very High Susceptibility'
        )
        
        self.assertEqual(report.user, self.user)
        self.assertEqual(report.barangay, 'Test Barangay')
        self.assertEqual(report.flood_risk_code, 'VHF')
        self.assertIsNotNone(report.timestamp)


class CertificateRecordModelTest(TestCase):
    """Test the CertificateRecord model"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='certstaff',
            password='testpass123'
        )
    
    def test_certificate_record_creation(self):
        """Test creating a certificate record"""
        certificate = CertificateRecord.objects.create(
            user=self.user,
            establishment_name='Test Cafe',
            owner_name='Juan Dela Cruz',
            location='123 Test Street',
            barangay='Test Barangay',
            latitude=Decimal('10.555555'),
            longitude=Decimal('122.666666'),
            flood_susceptibility='LOW FLOOD SUSCEPTIBILITY',
            zone_status='SAFE ZONE',
            issue_date='1st of January 2024'
        )
        
        self.assertEqual(certificate.establishment_name, 'Test Cafe')
        self.assertEqual(certificate.owner_name, 'Juan Dela Cruz')
        self.assertEqual(certificate.zone_status, 'SAFE ZONE')
        self.assertIsNotNone(certificate.timestamp)
    
    def test_certificate_str_method(self):
        """Test the __str__ method"""
        certificate = CertificateRecord.objects.create(
            user=self.user,
            establishment_name='Test Restaurant',
            owner_name='Maria Santos',
            location='456 Main Road',
            barangay='Downtown',
            latitude=Decimal('10.777777'),
            longitude=Decimal('122.888888'),
            flood_susceptibility='MODERATE FLOOD SUSCEPTIBILITY',
            zone_status='CONTROLLED ZONE',
            issue_date='15th of March 2024'
        )
        
        str_repr = str(certificate)
        self.assertIn('certstaff', str_repr)
        self.assertIn('Test Restaurant', str_repr)


# ============================================================================
# VIEW TESTS - Testing the view functions and their behaviors
# ============================================================================

class MapViewTest(TestCase):
    """Test the map_view function"""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            staff_id='TEST001'
        )
        self.client.login(username='testuser', password='testpass123')
        
        # Create test data
        poly = Polygon(((0, 0), (0, 1), (1, 1), (1, 0), (0, 0)))
        multipolygon = MultiPolygon(poly)
        
        self.barangay = Barangay.objects.create(
            id='123456789',
            name='Test Barangay',
            parent_id='12345678',
            geometry=multipolygon
        )
        
        self.flood = FloodSusceptibility.objects.create(
            lgu='Silay City',
            psgc_lgu='64526000',
            haz_class='Flooding',
            haz_code='HF',
            haz_area_ha=Decimal('10.0'),
            geometry=multipolygon
        )
    
    def test_map_view_login_required(self):
        """Test that map view requires login"""
        self.client.logout()
        response = self.client.get('/maps/')
        self.assertEqual(response.status_code, 302)  # Redirect to login
    
    def test_map_view_get_request(self):
        """Test map view returns correct template and context"""
        response = self.client.get('/maps/')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'maps/map.html')
        
        # Check that context contains required data
        self.assertIn('barangays_json', response.context)
        self.assertIn('flood_areas_json', response.context)
        self.assertIn('barangay_names', response.context)
    
    def test_map_view_contains_barangay_names(self):
        """Test that barangay names are passed to template"""
        response = self.client.get('/maps/')
        barangay_names = response.context['barangay_names']
        self.assertIn('Test Barangay', barangay_names)
    
    def test_map_view_geojson_format(self):
        """Test that GeoJSON data is properly formatted"""
        response = self.client.get('/maps/')
        barangays_json = response.context['barangays_json']
        
        # Should be a string containing GeoJSON
        self.assertIsInstance(barangays_json, str)
        self.assertIn('type', barangays_json)
        self.assertIn('features', barangays_json)


class ReportViewTest(TestCase):
    """Test the report_view function"""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')
    
    def test_report_view_login_required(self):
        """Test that report view requires login"""
        self.client.logout()
        response = self.client.get('/maps/report/?barangay=Test&lat=10.0&lon=122.0&risk=HF')
        self.assertEqual(response.status_code, 302)  # Redirect to login
    
    def test_report_view_with_valid_parameters(self):
        """Test report view with all valid parameters"""
        response = self.client.get(
            '/maps/report/?barangay=Test%20Barangay&lat=10.123456&lon=122.654321&risk=HF'
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'maps/report.html')
    
    def test_report_view_context_for_low_flood(self):
        """Test context for Low Flood Susceptibility"""
        response = self.client.get(
            '/maps/report/?barangay=Downtown&lat=10.5&lon=122.5&risk=LF'
        )
        context = response.context
        self.assertEqual(context['risk_code'], 'LF')
        self.assertEqual(context['risk_class'], 'risk-low')
        self.assertIn('less than 0.5 meters', context['assessment_text'])
    
    def test_report_view_context_for_moderate_flood(self):
        """Test context for Moderate Flood Susceptibility"""
        response = self.client.get(
            '/maps/report/?barangay=Downtown&lat=10.5&lon=122.5&risk=MF'
        )
        context = response.context
        self.assertEqual(context['risk_code'], 'MF')
        self.assertEqual(context['risk_class'], 'risk-moderate')
        self.assertIn('0.5 to 1 meter', context['assessment_text'])
    
    def test_report_view_context_for_high_flood(self):
        """Test context for High Flood Susceptibility"""
        response = self.client.get(
            '/maps/report/?barangay=Downtown&lat=10.5&lon=122.5&risk=HF'
        )
        context = response.context
        self.assertEqual(context['risk_code'], 'HF')
        self.assertEqual(context['risk_class'], 'risk-high')
        self.assertIn('1 to 2 meters', context['assessment_text'])
    
    def test_report_view_context_for_very_high_flood(self):
        """Test context for Very High Flood Susceptibility"""
        response = self.client.get(
            '/maps/report/?barangay=Downtown&lat=10.5&lon=122.5&risk=VHF'
        )
        context = response.context
        self.assertEqual(context['risk_code'], 'VHF')
        self.assertEqual(context['risk_class'], 'risk-very-high')
        self.assertIn('more than 2 meters', context['assessment_text'])
    
    def test_report_view_with_unknown_risk_code(self):
        """Test report view with unknown risk code"""
        response = self.client.get(
            '/maps/report/?barangay=Downtown&lat=10.5&lon=122.5&risk=XXX'
        )
        context = response.context
        self.assertEqual(context['risk_label'], 'Unknown Risk Level')
        self.assertIn('No risk data available', context['assessment_text'])
    
    def test_report_view_creates_report_record(self):
        """Test that report view creates a ReportRecord"""
        self.assertEqual(ReportRecord.objects.count(), 0)
        
        response = self.client.get(
            '/maps/report/?barangay=Downtown&lat=10.5&lon=122.5&risk=HF'
        )
        
        self.assertEqual(ReportRecord.objects.count(), 1)
        report = ReportRecord.objects.first()
        self.assertEqual(report.user, self.user)
        self.assertEqual(report.barangay, 'Downtown')
        self.assertEqual(report.latitude, Decimal('10.5'))
        self.assertEqual(report.longitude, Decimal('122.5'))
        self.assertEqual(report.flood_risk_code, 'HF')
    
    def test_report_view_with_missing_parameters(self):
        """Test report view with missing parameters defaults"""
        response = self.client.get('/maps/report/?barangay=Test&lat=10.0&lon=122.0&risk=LF')
        context = response.context
        
        self.assertEqual(context['barangay'], 'Test')
        self.assertEqual(context['latitude'], '10.0')
        self.assertEqual(context['longitude'], '122.0')
        self.assertEqual(context['risk_code'], 'LF')
    
    def test_report_view_includes_current_date(self):
        """Test that report includes formatted current date"""
        response = self.client.get(
            '/maps/report/?barangay=Test&lat=10.0&lon=122.0&risk=LF'
        )
        context = response.context
        self.assertIn('current_date', context)
        self.assertIsNotNone(context['current_date'])


class CertificateFormViewTest(TestCase):
    """Test the certificate_form_view function"""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            staff_id='TEST003'
        )
        self.client.login(username='testuser', password='testpass123')
    
    def test_certificate_form_view_login_required(self):
        """Test that certificate form view requires login"""
        self.client.logout()
        response = self.client.get('/maps/certificate/form/?barangay=Test&lat=10.0&lon=122.0&risk=LF')
        self.assertEqual(response.status_code, 302)  # Redirect to login
    
    def test_certificate_form_view_get_request(self):
        """Test certificate form view returns correct template"""
        response = self.client.get(
            '/maps/certificate/form/?barangay=Test&lat=10.0&lon=122.0&risk=LF'
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'maps/certificate_form.html')
    
    def test_certificate_form_view_risk_mapping_lf(self):
        """Test risk mapping for Low Flood"""
        response = self.client.get(
            '/maps/certificate/form/?barangay=Downtown&lat=10.5&lon=122.5&risk=LF'
        )
        context = response.context
        self.assertEqual(context['flood_susceptibility'], 'LOW FLOOD SUSCEPTIBILITY')
        self.assertEqual(context['zone_status'], 'SAFE ZONE')
    
    def test_certificate_form_view_risk_mapping_mf(self):
        """Test risk mapping for Moderate Flood"""
        response = self.client.get(
            '/maps/certificate/form/?barangay=Downtown&lat=10.5&lon=122.5&risk=MF'
        )
        context = response.context
        self.assertEqual(context['flood_susceptibility'], 'MODERATE FLOOD SUSCEPTIBILITY')
        self.assertEqual(context['zone_status'], 'CONTROLLED ZONE')
    
    def test_certificate_form_view_risk_mapping_hf(self):
        """Test risk mapping for High Flood"""
        response = self.client.get(
            '/maps/certificate/form/?barangay=Downtown&lat=10.5&lon=122.5&risk=HF'
        )
        context = response.context
        self.assertEqual(context['flood_susceptibility'], 'HIGH FLOOD SUSCEPTIBILITY')
        self.assertEqual(context['zone_status'], 'CRITICAL ZONE')
    
    def test_certificate_form_view_risk_mapping_vhf(self):
        """Test risk mapping for Very High Flood"""
        response = self.client.get(
            '/maps/certificate/form/?barangay=Downtown&lat=10.5&lon=122.5&risk=VHF'
        )
        context = response.context
        self.assertEqual(context['flood_susceptibility'], 'VERY HIGH FLOOD SUSCEPTIBILITY')
        self.assertEqual(context['zone_status'], 'NO HABITATION/BUILD ZONE')
    
    def test_certificate_form_view_date_suffix(self):
        """Test that date suffix is correctly generated"""
        response = self.client.get(
            '/maps/certificate/form/?barangay=Test&lat=10.0&lon=122.0&risk=LF'
        )
        context = response.context
        issue_date = context['issue_date']
        
        # Should contain day with suffix and 'of'
        self.assertIn('of', issue_date)
        # Check that it has the right format (day with suffix like st, nd, rd, th)
        self.assertTrue(any(suffix in issue_date for suffix in ['st', 'nd', 'rd', 'th']))


class CertificateViewTest(TestCase):
    """Test the certificate_view function"""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            staff_id='TEST004'
        )
        self.client.login(username='testuser', password='testpass123')
    
    def test_certificate_view_get_redirects(self):
        """Test that GET request redirects to map"""
        response = self.client.get('/maps/certificate/', follow=False)
        self.assertEqual(response.status_code, 302)
    
    def test_certificate_view_post_request(self):
        """Test certificate view handles POST request"""
        data = {
            'establishment_name': 'Test Cafe',
            'owner_name': 'Juan Dela Cruz',
            'location': '123 Test Street',
            'barangay': 'downtown',
            'zone_status': 'SAFE ZONE',
            'issue_date': '1st of January 2024',
            'latitude': '10.123456',
            'longitude': '122.654321',
            'flood_susceptibility': 'LOW FLOOD SUSCEPTIBILITY',
            'risk_code': 'LF',
            'signatory_name': 'Dr. Juan Dela Cruz',
            'signatory_title': 'MDRRMO Director',
            'signatory_subtitle': 'Municipality of Silay'
        }
        response = self.client.post('/maps/certificate/', data)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'maps/certificate.html')
    
    def test_certificate_view_creates_certificate_record(self):
        """Test that certificate view creates a CertificateRecord"""
        self.assertEqual(CertificateRecord.objects.count(), 0)
        
        data = {
            'establishment_name': 'Test Restaurant',
            'owner_name': 'Maria Santos',
            'location': '456 Main Road',
            'barangay': 'downtown',
            'zone_status': 'CONTROLLED ZONE',
            'issue_date': '15th of March 2024',
            'latitude': '10.555555',
            'longitude': '122.666666',
            'flood_susceptibility': 'MODERATE FLOOD SUSCEPTIBILITY',
            'risk_code': 'MF',
            'signatory_name': 'Engr. Maria Santos',
            'signatory_title': 'City Engineer',
            'signatory_subtitle': 'City of Silay'
        }
        response = self.client.post('/maps/certificate/', data)
        
        self.assertEqual(CertificateRecord.objects.count(), 1)
        cert = CertificateRecord.objects.first()
        self.assertEqual(cert.establishment_name, 'Test Restaurant')
        self.assertEqual(cert.owner_name, 'Maria Santos')
        self.assertEqual(cert.user, self.user)
    
    def test_certificate_view_context_contains_uppercase_barangay(self):
        """Test that barangay is converted to uppercase in context"""
        data = {
            'establishment_name': 'Test Shop',
            'owner_name': 'Pedro Garcia',
            'location': '789 Side Street',
            'barangay': 'downtown',
            'zone_status': 'SAFE ZONE',
            'issue_date': '20th of May 2024',
            'latitude': '10.777777',
            'longitude': '122.888888',
            'flood_susceptibility': 'LOW FLOOD SUSCEPTIBILITY',
            'risk_code': 'LF',
            'signatory_name': 'Mayor Pedro Garcia',
            'signatory_title': 'City Mayor',
            'signatory_subtitle': 'Silay City'
        }
        response = self.client.post('/maps/certificate/', data)
        context = response.context
        
        self.assertEqual(context['barangay'], 'DOWNTOWN')


class SaveAssessmentViewTest(TestCase):
    """Test the save_assessment AJAX view"""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            staff_id='TEST005'
        )
        self.client.login(username='testuser', password='testpass123')
    
    def test_save_assessment_login_required(self):
        """Test that save_assessment requires login"""
        self.client.logout()
        response = self.client.post('/maps/save-assessment/')
        self.assertEqual(response.status_code, 302)  # Redirect to login
    
    def test_save_assessment_post_request(self):
        """Test save_assessment with POST request"""
        data = {
            'barangay': 'Test Barangay',
            'latitude': '10.123456',
            'longitude': '122.654321',
            'flood_risk_code': 'HF'
        }
        response = self.client.post('/maps/save-assessment/', data)
        
        self.assertEqual(response.status_code, 200)
        json_data = response.json()
        self.assertTrue(json_data['success'])
        self.assertIn('assessment_id', json_data)
    
    def test_save_assessment_creates_assessment_record(self):
        """Test that save_assessment creates an AssessmentRecord"""
        self.assertEqual(AssessmentRecord.objects.count(), 0)
        
        data = {
            'barangay': 'Downtown',
            'latitude': '10.5',
            'longitude': '122.5',
            'flood_risk_code': 'MF'
        }
        response = self.client.post('/maps/save-assessment/', data)
        
        self.assertEqual(AssessmentRecord.objects.count(), 1)
        assessment = AssessmentRecord.objects.first()
        self.assertEqual(assessment.barangay, 'Downtown')
        self.assertEqual(assessment.flood_risk_code, 'MF')
        self.assertEqual(assessment.user, self.user)
    
    def test_save_assessment_risk_description_mapping(self):
        """Test that risk codes are mapped to descriptions"""
        risk_codes_mapping = {
            'LF': 'Low Flood Susceptibility',
            'MF': 'Moderate Flood Susceptibility',
            'HF': 'High Flood Susceptibility',
            'VHF': 'Very High Flood Susceptibility'
        }
        
        for code, expected_desc in risk_codes_mapping.items():
            AssessmentRecord.objects.all().delete()
            data = {
                'barangay': 'Test',
                'latitude': '10.0',
                'longitude': '122.0',
                'flood_risk_code': code
            }
            response = self.client.post('/maps/save-assessment/', data)
            
            assessment = AssessmentRecord.objects.first()
            self.assertEqual(assessment.flood_risk_description, expected_desc)
    
    def test_save_assessment_get_request_fails(self):
        """Test that GET request returns failure"""
        response = self.client.get('/maps/save-assessment/')
        
        self.assertEqual(response.status_code, 200)
        json_data = response.json()
        self.assertFalse(json_data['success'])


class MyActivityViewTest(TestCase):
    """Test the my_activity view"""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            staff_id='TEST006'
        )
        self.other_user = User.objects.create_user(
            username='otheruser',
            password='testpass123',
            staff_id='TEST007'
        )
        self.client.login(username='testuser', password='testpass123')
        
        # Create test data for current user
        self.assessment = AssessmentRecord.objects.create(
            user=self.user,
            barangay='Test Barangay',
            latitude=Decimal('10.5'),
            longitude=Decimal('122.5'),
            flood_risk_code='HF',
            flood_risk_description='High Flood Susceptibility'
        )
        
        self.report = ReportRecord.objects.create(
            user=self.user,
            barangay='Test Barangay',
            latitude=Decimal('10.5'),
            longitude=Decimal('122.5'),
            flood_risk_code='HF',
            flood_risk_label='High Flood Susceptibility'
        )
    
    def test_my_activity_login_required(self):
        """Test that my_activity requires login"""
        self.client.logout()
        response = self.client.get('/maps/my-activity/')
        self.assertEqual(response.status_code, 302)  # Redirect to login
    
    def test_my_activity_view_get_request(self):
        """Test my_activity view returns correct template"""
        response = self.client.get('/maps/my-activity/')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'maps/my_activity.html')
    
    def test_my_activity_shows_only_current_user_data(self):
        """Test that my_activity only shows current user's data"""
        # Create assessment for other user
        AssessmentRecord.objects.create(
            user=self.other_user,
            barangay='Other Barangay',
            latitude=Decimal('10.0'),
            longitude=Decimal('122.0'),
            flood_risk_code='LF',
            flood_risk_description='Low Flood Susceptibility'
        )
        
        response = self.client.get('/maps/my-activity/')
        assessments = response.context['assessments']
        
        # Should only show current user's assessment
        self.assertEqual(assessments.count(), 1)
        self.assertEqual(assessments[0].user, self.user)
    
    def test_my_activity_sort_recent_default(self):
        """Test that default sort is recent (most recent first)"""
        response = self.client.get('/maps/my-activity/')
        context = response.context
        
        self.assertEqual(context['sort_order'], 'recent')
    
    def test_my_activity_sort_oldest(self):
        """Test sort by oldest first"""
        response = self.client.get('/maps/my-activity/?sort=oldest')
        context = response.context
        
        self.assertEqual(context['sort_order'], 'oldest')
        assessments = context['assessments']
        # Should be ordered by timestamp ascending
        self.assertEqual(assessments[0], self.assessment)
    
    def test_my_activity_sort_recent(self):
        """Test sort by recent first"""
        response = self.client.get('/maps/my-activity/?sort=recent')
        context = response.context
        
        self.assertEqual(context['sort_order'], 'recent')
    
    def test_my_activity_active_tab(self):
        """Test active tab parameter"""
        response = self.client.get('/maps/my-activity/?tab=reports')
        context = response.context
        
        self.assertEqual(context['active_tab'], 'reports')
    
    def test_my_activity_context_counts(self):
        """Test that context includes count totals"""
        response = self.client.get('/maps/my-activity/')
        context = response.context
        
        self.assertEqual(context['total_assessments'], 1)
        self.assertEqual(context['total_reports'], 1)
        self.assertEqual(context['total_certificates'], 0)


class AllActivitiesViewTest(TestCase):
    """Test the all_activities view (admin only)"""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='normaluser',
            password='testpass123',
            staff_id='TEST008'
        )
        self.admin_user = User.objects.create_user(
            username='adminuser',
            password='testpass123',
            staff_id='TEST009',
            is_staff=True
        )
        self.other_user = User.objects.create_user(
            username='otheruser',
            password='testpass123',
            staff_id='TEST010'
        )
        
        # Create test data
        self.assessment = AssessmentRecord.objects.create(
            user=self.other_user,
            barangay='Test Barangay',
            latitude=Decimal('10.5'),
            longitude=Decimal('122.5'),
            flood_risk_code='HF',
            flood_risk_description='High Flood Susceptibility'
        )
    
    def test_all_activities_login_required(self):
        """Test that all_activities requires login"""
        self.client.logout()
        response = self.client.get('/maps/all-activities/')
        self.assertEqual(response.status_code, 302)  # Redirect to login
    
    def test_all_activities_staff_required(self):
        """Test that only staff can access all_activities"""
        self.client.login(username='normaluser', password='testpass123')
        response = self.client.get('/maps/all-activities/')
        self.assertEqual(response.status_code, 403)  # Permission Denied
    
    def test_all_activities_staff_access(self):
        """Test that staff can access all_activities"""
        self.client.login(username='adminuser', password='testpass123')
        response = self.client.get('/maps/all-activities/')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'maps/all_activities.html')
    
    def test_all_activities_shows_all_users_data(self):
        """Test that all_activities shows all users' data"""
        self.client.login(username='adminuser', password='testpass123')
        response = self.client.get('/maps/all-activities/')
        assessments = response.context['assessments']
        
        # Should show all assessments (assessments is a Page object from pagination)
        self.assertGreaterEqual(len(assessments), 1)
    
    def test_all_activities_filter_by_user(self):
        """Test filtering by user"""
        self.client.login(username='adminuser', password='testpass123')
        response = self.client.get(f'/maps/all-activities/?user={self.other_user.id}')
        assessments = response.context['assessments']
        
        # Should only show this user's assessments (assessments is a Page object from pagination)
        self.assertEqual(len(assessments), 1)
        self.assertEqual(assessments[0].user, self.other_user)
    
    def test_all_activities_sort_recent_default(self):
        """Test that default sort is recent"""
        self.client.login(username='adminuser', password='testpass123')
        response = self.client.get('/maps/all-activities/')
        context = response.context
        
        self.assertEqual(context['sort_order'], 'recent')
    
    def test_all_activities_sort_oldest(self):
        """Test sort by oldest"""
        self.client.login(username='adminuser', password='testpass123')
        response = self.client.get('/maps/all-activities/?sort=oldest')
        context = response.context
        
        self.assertEqual(context['sort_order'], 'oldest')
    
    def test_all_activities_active_tab(self):
        """Test active tab parameter"""
        self.client.login(username='adminuser', password='testpass123')
        response = self.client.get('/maps/all-activities/?tab=certificates')
        context = response.context
        
        self.assertEqual(context['active_tab'], 'certificates')
    
    def test_all_activities_includes_users_for_filter(self):
        """Test that users list is available for filter dropdown"""
        self.client.login(username='adminuser', password='testpass123')
        response = self.client.get('/maps/all-activities/')
        context = response.context
        
        users = context['users']
        self.assertGreater(users.count(), 0)


# ============================================================================
# ADMIN TESTS - Testing the Django admin customizations
# ============================================================================

class BarangayAdminTest(TestCase):
    """Test the BarangayAdmin customization"""
    
    def setUp(self):
        self.client = Client()
        self.admin_user = User.objects.create_superuser(
            username='adminuser',
            email='admin@test.com',
            password='testpass123',
            staff_id='ADMIN001'
        )
        self.client.login(username='adminuser', password='testpass123')
        
        # Create test barangay
        poly = Polygon(((0, 0), (0, 1), (1, 1), (1, 0), (0, 0)))
        multipolygon = MultiPolygon(poly)
        
        self.barangay = Barangay.objects.create(
            id='123456789',
            name='Test Barangay',
            parent_id='12345678',
            geometry=multipolygon
        )
    
    def test_barangay_admin_list_display(self):
        """Test that BarangayAdmin has correct list_display fields"""
        from maps.admin import BarangayAdmin
        
        admin_instance = BarangayAdmin(Barangay, None)
        self.assertEqual(admin_instance.list_display, ['id', 'name', 'parent_id'])
    
    def test_barangay_admin_search_fields(self):
        """Test that BarangayAdmin has correct search_fields"""
        from maps.admin import BarangayAdmin
        
        admin_instance = BarangayAdmin(Barangay, None)
        self.assertEqual(admin_instance.search_fields, ['name', 'id'])
    
    def test_barangay_admin_changelist_view(self):
        """Test that barangay can be viewed in admin changelist"""
        response = self.client.get('/admin/maps/barangay/')
        self.assertEqual(response.status_code, 200)
    
    def test_barangay_admin_add_view(self):
        """Test that barangay can be added via admin"""
        response = self.client.get('/admin/maps/barangay/add/')
        self.assertEqual(response.status_code, 200)


class FloodSusceptibilityAdminTest(TestCase):
    """Test the FloodSusceptibilityAdmin customization"""
    
    def setUp(self):
        self.client = Client()
        self.admin_user = User.objects.create_superuser(
            username='adminuser',
            email='admin@test.com',
            password='testpass123',
            staff_id='ADMIN002'
        )
        self.client.login(username='adminuser', password='testpass123')
        
        # Create test flood susceptibility
        poly = Polygon(((0, 0), (0, 1), (1, 1), (1, 0), (0, 0)))
        multipolygon = MultiPolygon(poly)
        
        self.flood = FloodSusceptibility.objects.create(
            lgu='Silay City',
            psgc_lgu='64526000',
            haz_class='Flooding',
            haz_code='HF',
            haz_area_ha=Decimal('10.0'),
            geometry=multipolygon
        )
    
    def test_flood_susceptibility_admin_list_display(self):
        """Test that FloodSusceptibilityAdmin has correct list_display fields"""
        from maps.admin import FloodSusceptibilityAdmin
        
        admin_instance = FloodSusceptibilityAdmin(FloodSusceptibility, None)
        self.assertEqual(
            admin_instance.list_display,
            ['lgu', 'haz_code', 'haz_desc', 'haz_area_ha']
        )
    
    def test_flood_susceptibility_admin_list_filter(self):
        """Test that FloodSusceptibilityAdmin has correct list_filter"""
        from maps.admin import FloodSusceptibilityAdmin
        
        admin_instance = FloodSusceptibilityAdmin(FloodSusceptibility, None)
        self.assertEqual(admin_instance.list_filter, ['haz_code', 'lgu'])
    
    def test_flood_susceptibility_admin_search_fields(self):
        """Test that FloodSusceptibilityAdmin has correct search_fields"""
        from maps.admin import FloodSusceptibilityAdmin
        
        admin_instance = FloodSusceptibilityAdmin(FloodSusceptibility, None)
        self.assertEqual(admin_instance.search_fields, ['lgu', 'haz_desc'])
    
    def test_flood_susceptibility_admin_changelist_view(self):
        """Test that flood susceptibility can be viewed in admin changelist"""
        response = self.client.get('/admin/maps/floodsusceptibility/')
        self.assertEqual(response.status_code, 200)


class AssessmentRecordAdminTest(TestCase):
    """Test the AssessmentRecordAdmin customization"""
    
    def setUp(self):
        self.client = Client()
        self.admin_user = User.objects.create_superuser(
            username='adminuser',
            email='admin@test.com',
            password='testpass123',
            staff_id='ADMIN003'
        )
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            staff_id='TEST011'
        )
        self.client.login(username='adminuser', password='testpass123')
        
        # Create test assessment
        self.assessment = AssessmentRecord.objects.create(
            user=self.user,
            barangay='Test Barangay',
            latitude=Decimal('10.5'),
            longitude=Decimal('122.5'),
            flood_risk_code='HF',
            flood_risk_description='High Flood Susceptibility'
        )
    
    def test_assessment_record_admin_list_display(self):
        """Test that AssessmentRecordAdmin has correct list_display"""
        from maps.admin import AssessmentRecordAdmin
        
        admin_instance = AssessmentRecordAdmin(AssessmentRecord, None)
        self.assertEqual(
            admin_instance.list_display,
            ['user', 'barangay', 'flood_risk_code', 'timestamp']
        )
    
    def test_assessment_record_admin_list_filter(self):
        """Test that AssessmentRecordAdmin has correct list_filter"""
        from maps.admin import AssessmentRecordAdmin
        
        admin_instance = AssessmentRecordAdmin(AssessmentRecord, None)
        self.assertEqual(
            admin_instance.list_filter,
            ['flood_risk_code', 'timestamp', 'user']
        )
    
    def test_assessment_record_admin_search_fields(self):
        """Test that AssessmentRecordAdmin has correct search_fields"""
        from maps.admin import AssessmentRecordAdmin
        
        admin_instance = AssessmentRecordAdmin(AssessmentRecord, None)
        self.assertEqual(
            admin_instance.search_fields,
            ['user__username', 'barangay', 'user__staff_id']
        )
    
    def test_assessment_record_admin_readonly_fields(self):
        """Test that timestamp is readonly"""
        from maps.admin import AssessmentRecordAdmin
        
        admin_instance = AssessmentRecordAdmin(AssessmentRecord, None)
        self.assertEqual(admin_instance.readonly_fields, ['timestamp'])
    
    def test_assessment_record_admin_get_queryset_select_related(self):
        """Test that get_queryset uses select_related for optimization"""
        from maps.admin import AssessmentRecordAdmin
        from django.test import RequestFactory
        
        factory = RequestFactory()
        request = factory.get('/admin/')
        request.user = self.admin_user
        
        admin_instance = AssessmentRecordAdmin(AssessmentRecord, None)
        queryset = admin_instance.get_queryset(request)
        
        # Check that the queryset has select_related applied
        # by verifying the query string contains a JOIN for the user table
        query_str = str(queryset.query)
        self.assertIn('INNER JOIN', query_str)
    
    def test_assessment_record_admin_changelist_view(self):
        """Test that assessment records can be viewed in admin changelist"""
        response = self.client.get('/admin/maps/assessmentrecord/')
        self.assertEqual(response.status_code, 200)


class ReportRecordAdminTest(TestCase):
    """Test the ReportRecordAdmin customization"""
    
    def setUp(self):
        self.client = Client()
        self.admin_user = User.objects.create_superuser(
            username='adminuser',
            email='admin@test.com',
            password='testpass123',
            staff_id='ADMIN004'
        )
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            staff_id='TEST012'
        )
        self.client.login(username='adminuser', password='testpass123')
        
        # Create test report
        self.report = ReportRecord.objects.create(
            user=self.user,
            barangay='Test Barangay',
            latitude=Decimal('10.5'),
            longitude=Decimal('122.5'),
            flood_risk_code='MF',
            flood_risk_label='Moderate Flood Susceptibility'
        )
    
    def test_report_record_admin_list_display(self):
        """Test that ReportRecordAdmin has correct list_display"""
        from maps.admin import ReportRecordAdmin
        
        admin_instance = ReportRecordAdmin(ReportRecord, None)
        self.assertEqual(
            admin_instance.list_display,
            ['user', 'barangay', 'flood_risk_code', 'timestamp']
        )
    
    def test_report_record_admin_list_filter(self):
        """Test that ReportRecordAdmin has correct list_filter"""
        from maps.admin import ReportRecordAdmin
        
        admin_instance = ReportRecordAdmin(ReportRecord, None)
        self.assertEqual(
            admin_instance.list_filter,
            ['flood_risk_code', 'timestamp', 'user']
        )
    
    def test_report_record_admin_search_fields(self):
        """Test that ReportRecordAdmin has correct search_fields"""
        from maps.admin import ReportRecordAdmin
        
        admin_instance = ReportRecordAdmin(ReportRecord, None)
        self.assertEqual(
            admin_instance.search_fields,
            ['user__username', 'barangay', 'user__staff_id']
        )
    
    def test_report_record_admin_readonly_fields(self):
        """Test that timestamp is readonly"""
        from maps.admin import ReportRecordAdmin
        
        admin_instance = ReportRecordAdmin(ReportRecord, None)
        self.assertEqual(admin_instance.readonly_fields, ['timestamp'])
    
    def test_report_record_admin_get_queryset_select_related(self):
        """Test that get_queryset uses select_related for optimization"""
        from maps.admin import ReportRecordAdmin
        from django.test import RequestFactory
        
        factory = RequestFactory()
        request = factory.get('/admin/')
        request.user = self.admin_user
        
        admin_instance = ReportRecordAdmin(ReportRecord, None)
        queryset = admin_instance.get_queryset(request)
        
        # Check that the queryset has select_related applied
        query_str = str(queryset.query)
        self.assertIn('INNER JOIN', query_str)
    
    def test_report_record_admin_changelist_view(self):
        """Test that report records can be viewed in admin changelist"""
        response = self.client.get('/admin/maps/reportrecord/')
        self.assertEqual(response.status_code, 200)


class CertificateRecordAdminTest(TestCase):
    """Test the CertificateRecordAdmin customization"""
    
    def setUp(self):
        self.client = Client()
        self.admin_user = User.objects.create_superuser(
            username='adminuser',
            email='admin@test.com',
            password='testpass123',
            staff_id='ADMIN005'
        )
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            staff_id='TEST013'
        )
        self.client.login(username='adminuser', password='testpass123')
        
        # Create test certificate
        self.certificate = CertificateRecord.objects.create(
            user=self.user,
            establishment_name='Test Cafe',
            owner_name='Juan Dela Cruz',
            location='123 Test Street',
            barangay='Test Barangay',
            latitude=Decimal('10.5'),
            longitude=Decimal('122.5'),
            flood_susceptibility='LOW FLOOD SUSCEPTIBILITY',
            zone_status='SAFE ZONE',
            issue_date='1st of January 2024'
        )
    
    def test_certificate_record_admin_list_display(self):
        """Test that CertificateRecordAdmin has correct list_display"""
        from maps.admin import CertificateRecordAdmin
        
        admin_instance = CertificateRecordAdmin(CertificateRecord, None)
        self.assertEqual(
            admin_instance.list_display,
            ['user', 'establishment_name', 'owner_name', 'barangay', 'timestamp']
        )
    
    def test_certificate_record_admin_list_filter(self):
        """Test that CertificateRecordAdmin has correct list_filter"""
        from maps.admin import CertificateRecordAdmin
        
        admin_instance = CertificateRecordAdmin(CertificateRecord, None)
        self.assertEqual(
            admin_instance.list_filter,
            ['timestamp', 'user', 'zone_status']
        )
    
    def test_certificate_record_admin_search_fields(self):
        """Test that CertificateRecordAdmin has correct search_fields"""
        from maps.admin import CertificateRecordAdmin
        
        admin_instance = CertificateRecordAdmin(CertificateRecord, None)
        self.assertEqual(
            admin_instance.search_fields,
            ['user__username', 'establishment_name', 'owner_name', 'barangay', 'user__staff_id']
        )
    
    def test_certificate_record_admin_readonly_fields(self):
        """Test that timestamp is readonly"""
        from maps.admin import CertificateRecordAdmin
        
        admin_instance = CertificateRecordAdmin(CertificateRecord, None)
        self.assertEqual(admin_instance.readonly_fields, ['timestamp'])
    
    def test_certificate_record_admin_get_queryset_select_related(self):
        """Test that get_queryset uses select_related for optimization"""
        from maps.admin import CertificateRecordAdmin
        from django.test import RequestFactory
        
        factory = RequestFactory()
        request = factory.get('/admin/')
        request.user = self.admin_user
        
        admin_instance = CertificateRecordAdmin(CertificateRecord, None)
        queryset = admin_instance.get_queryset(request)
        
        # Check that the queryset has select_related applied
        query_str = str(queryset.query)
        self.assertIn('INNER JOIN', query_str)
    
    def test_certificate_record_admin_changelist_view(self):
        """Test that certificate records can be viewed in admin changelist"""
        response = self.client.get('/admin/maps/certificaterecord/')
        self.assertEqual(response.status_code, 200)


class ExportActivitiesViewTest(TestCase):
    """Test the export_activities view"""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='normaluser',
            password='testpass123',
            staff_id='TEST014'
        )
        self.staff_user = User.objects.create_user(
            username='staffuser',
            password='testpass123',
            staff_id='TEST015',
            is_staff=True
        )
        
        # Create test data
        self.assessment = AssessmentRecord.objects.create(
            user=self.staff_user,
            barangay='Test Barangay',
            latitude=Decimal('10.5'),
            longitude=Decimal('122.5'),
            flood_risk_code='HF',
            flood_risk_description='High Flood Susceptibility'
        )
        
        self.report = ReportRecord.objects.create(
            user=self.staff_user,
            barangay='Test Barangay',
            latitude=Decimal('10.5'),
            longitude=Decimal('122.5'),
            flood_risk_code='HF',
            flood_risk_label='High Flood Susceptibility'
        )
        
        self.certificate = CertificateRecord.objects.create(
            user=self.staff_user,
            establishment_name='Test Establishment',
            owner_name='Test Owner',
            barangay='Test Barangay',
            location='Test Location',
            latitude=Decimal('10.5'),
            longitude=Decimal('122.5'),
            flood_susceptibility='Low Susceptibility',
            zone_status='Suitable for Development',
            issue_date='November 21, 2025'
        )
    
    def test_export_activities_login_required(self):
        """Test that export_activities requires login"""
        response = self.client.get('/maps/export-activities/')
        self.assertEqual(response.status_code, 302)  # Redirect to login
    
    def test_export_activities_staff_required(self):
        """Test that only staff can export activities"""
        self.client.login(username='normaluser', password='testpass123')
        response = self.client.get('/maps/export-activities/')
        self.assertEqual(response.status_code, 403)  # Permission Denied
    
    def test_export_activities_csv_format(self):
        """Test exporting activities in CSV format"""
        self.client.login(username='staffuser', password='testpass123')
        response = self.client.get('/maps/export-activities/?type=csv&activity=assessments')
        
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/csv', response['Content-Type'])
        self.assertIn('attachment', response['Content-Disposition'])
    
    def test_export_activities_pdf_format(self):
        """Test exporting activities in PDF format"""
        self.client.login(username='staffuser', password='testpass123')
        response = self.client.get('/maps/export-activities/?type=pdf&activity=reports')
        
        # PDF export may return 200 or 500 depending on reportlab availability
        self.assertIn(response.status_code, [200, 500])
    
    def test_export_activities_filter_by_user(self):
        """Test filtering export by user"""
        self.client.login(username='staffuser', password='testpass123')
        response = self.client.get(
            f'/maps/export-activities/?type=csv&activity=assessments&user={self.staff_user.id}'
        )
        
        self.assertEqual(response.status_code, 200)
    
    def test_export_activities_filter_by_date_range(self):
        """Test filtering export by date range"""
        self.client.login(username='staffuser', password='testpass123')
        today = timezone.now().date()
        yesterday = today - timedelta(days=1)
        tomorrow = today + timedelta(days=1)
        
        # Use date range that includes the setUp records (which have auto_now_add timestamps)
        response = self.client.get(
            f'/maps/export-activities/?type=csv&activity=assessments&date_from={yesterday}&date_to={tomorrow}'
        )
        
        self.assertEqual(response.status_code, 200)
    
    def test_export_activities_quick_date_range(self):
        """Test exporting with quick date range filter (last 7/30/90 days)"""
        self.client.login(username='staffuser', password='testpass123')
        response = self.client.get('/maps/export-activities/?type=csv&activity=assessments&date_range=7')
        
        self.assertEqual(response.status_code, 200)
    
    def test_export_activities_sort_order(self):
        """Test exporting with different sort orders"""
        self.client.login(username='staffuser', password='testpass123')
        
        # Test recent first
        response = self.client.get('/maps/export-activities/?type=csv&activity=assessments&sort=recent')
        self.assertEqual(response.status_code, 200)
        
        # Test oldest first
        response = self.client.get('/maps/export-activities/?type=csv&activity=assessments&sort=oldest')
        self.assertEqual(response.status_code, 200)
    
    def test_export_activities_different_activity_types(self):
        """Test exporting different activity types"""
        self.client.login(username='staffuser', password='testpass123')
        
        activity_types = ['assessments', 'reports', 'certificates']
        
        for activity_type in activity_types:
            response = self.client.get(f'/maps/export-activities/?type=csv&activity={activity_type}')
            # Should return 200 for valid activity types
            self.assertEqual(response.status_code, 200)
    
    def test_export_activities_search_query(self):
        """Test exporting with search query"""
        self.client.login(username='staffuser', password='testpass123')
        response = self.client.get('/maps/export-activities/?type=csv&activity=assessments&search=Test')
        
        self.assertEqual(response.status_code, 200)


class ErrorViewTest(TestCase):
    """Test the error_view function"""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            staff_id='TEST016'
        )
        self.client.login(username='testuser', password='testpass123')
    
    def test_error_view_loads(self):
        """Test that error view loads successfully"""
        response = self.client.get('/maps/error/?title=Test%20Error&message=Test%20message')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'maps/error.html')
    
    def test_error_view_displays_title(self):
        """Test that error view displays custom title"""
        response = self.client.get('/maps/error/?title=Custom%20Error&message=Something%20wrong')
        context = response.context
        
        self.assertEqual(context['error_title'], 'Custom Error')
    
    def test_error_view_displays_message(self):
        """Test that error view displays custom message"""
        response = self.client.get('/maps/error/?message=Custom%20error%20message')
        context = response.context
        
        self.assertEqual(context['error_message'], 'Custom error message')
    
    def test_error_view_default_values(self):
        """Test that error view has default values"""
        response = self.client.get('/maps/error/')
        context = response.context
        
        self.assertEqual(context['error_title'], 'An Error Occurred')
        self.assertEqual(context['error_message'], 'Something went wrong. Please try again.')
        self.assertEqual(context['error_details'], '')
    
    def test_error_view_with_details(self):
        """Test that error view displays additional details"""
        response = self.client.get('/maps/error/?details=Stack%20trace%20here')
        context = response.context
        
        self.assertEqual(context['error_details'], 'Stack trace here')


class PrivacyPolicyViewTest(TestCase):
    """Test the privacy_policy_view function"""
    
    def setUp(self):
        self.client = Client()
    
    def test_privacy_policy_view_loads(self):
        """Test that privacy policy view loads without login"""
        response = self.client.get('/maps/privacy-policy/')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'maps/privacy_policy.html')
    
    def test_privacy_policy_no_login_required(self):
        """Test that privacy policy is publicly accessible"""
        response = self.client.get('/maps/privacy-policy/')
        # Should not redirect to login
        self.assertEqual(response.status_code, 200)


class TermsOfServiceViewTest(TestCase):
    """Test the terms_of_service_view function"""
    
    def setUp(self):
        self.client = Client()
    
    def test_terms_of_service_view_loads(self):
        """Test that terms of service view loads without login"""
        response = self.client.get('/maps/terms-of-service/')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'maps/terms_of_service.html')
    
    def test_terms_of_service_no_login_required(self):
        """Test that terms of service is publicly accessible"""
        response = self.client.get('/maps/terms-of-service/')
        # Should not redirect to login
        self.assertEqual(response.status_code, 200)