#!/usr/bin/env python3
"""
Tests fuer ki-business-roi-analysis - Evidence-Based Development.
Alle Tests müssen bestanden sein bevor das Projekt als FERTIG gilt.
"""

import unittest
import sys
import os

# Füge Projektpfad hinzu
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from roi_analyzer import ROIAnalyzer

class TestROICalculator(unittest.TestCase):
    """Test-Suite für die ROI-Analyse des KI-Server-Business"""

    def test_1_detaillierte_kostenanalyse(self):
        """Test: Detaillierte Kostenanalyse mit allen relevanten Positionen"""
        
        # Teste Hardware-Kosten-Funktion
        hardware = ROIAnalyzer.calculate_hardware_costs("standard")
        total = sum(hardware.values())
        
        # Muss dict zurückgeben
        self.assertIsInstance(hardware, dict)
        
        # Muss alle Kategorien enthalten
        required_categories = [
            "server_hardware", "gpus", "ram", "storage", 
            "psu", "cooling", "case", "misc"
        ]
        for category in required_categories:
            self.assertIn(category, hardware)
            self.assertIsInstance(hardware[category], (int, float))
            self.assertGreater(hardware[category], 0)
        
        # Gesamtkosten müssen realistisch sein
        total_hardware = sum(hardware.values())
        self.assertGreaterEqual(total_hardware, 15000)
        self.assertLessEqual(total_hardware, 25000)
        
        # Teste Betriebskosten
        operating = ROIAnalyzer.calculate_operating_costs("standard", 12)
        self.assertIn("monthly", operating)
        self.assertIn("yearly", operating)
        
        # Alle Kostenkategorien müssen vorhanden sein
        required_op = ["electricity", "cooling", "maintenance", "internet", "backup", "insurance"]
        for op in required_op:
            self.assertIn(op, operating["monthly"])
            self.assertIsInstance(operating["monthly"][op], (int, float))

    def test_2_einnahmen_szenarien_fuer_3_nischen(self):
        """Test: Einnahmen-Szenarien für alle 3 Nischen (Medical, Steuer, Recht)"""
        
        # Teste alle 3 Nischen
        niches = ["medical", "tax", "legal"]
        
        for niche in niches:
            revenue = ROIAnalyzer.calculate_projected_revenue(niche, 5, "standard")
            
            # Muss Modelle enthalten
            self.assertIn("per_client", revenue)
            self.assertIn("monthly", revenue)
            self.assertIn("yearly", revenue)
            
            # Revenue pro Client muss realistisch sein
            self.assertGreater(revenue["per_client"], 500)
            self.assertLess(revenue["per_client"], 6000)
            
            # Monatliche und jährliche Einnahmen müssen korrekt sein
            self.assertEqual(revenue["yearly"], revenue["monthly"] * 12)

    def test_3_break_even_zeitpunkt(self):
        """Test: Break-Even-Zeitpunkt für verschiedene Konfigurationen"""
        
        # Teste verschiedene Konfigurationen
        configs = ["entry", "standard", "premium"]
        
        for config in configs:
            break_even = ROIAnalyzer.calculate_break_even(config, "medical", 8)
            
            # Muss alle Felder enthalten
            self.assertIn("months", break_even)
            self.assertIn("years", break_even)
            self.assertIn("total_investment", break_even)
            self.assertIn("monthly_profit", break_even)
            
            # Break-even muss realistisch sein (6-36 Monate)
            if break_even["months"] != float('inf'):
                self.assertGreaterEqual(break_even["months"], 6)
                self.assertLessEqual(break_even["months"], 36)

    def test_4_roi_rechnung_1_3_jahre(self):
        """Test: ROI-Rechnung für 1-3 Jahre"""
        
        roi_1_year = ROIAnalyzer.calculate_roi("standard", "medical", 8, years=1)
        roi_3_year = ROIAnalyzer.calculate_roi("standard", "medical", 8, years=3)
        
        # Muss % und absoluten Betrag enthalten
        for roi in [roi_1_year, roi_3_year]:
            self.assertIn("percentage", roi)
            self.assertIn("absolute", roi)
            self.assertIn("total_revenue", roi)
            self.assertIn("total_cost", roi)
            
            # Werte müssen numerisch sein
            self.assertIsInstance(roi["percentage"], (int, float))
            self.assertIsInstance(roi["absolute"], (int, float))

    def test_5_sensitivitätsanalyse(self):
        """Test: Sensitivitätsanalyse verschiedener Faktoren"""
        
        analysis = ROIAnalyzer.run_sensitivity_analysis(
            config="standard", 
            niche="medical", 
            clients=5,
            factors=["electricity_cost", "client_acquisition"]
        )
        
        # Muss dict sein
        self.assertIsInstance(analysis, dict)
        
        for factor in ["electricity_cost", "client_acquisition"]:
            self.assertIn(factor, analysis)
            factor_data = analysis[factor]
            
            # Muss baseline, low, high Szenarien haben
            self.assertIn("baseline", factor_data)
            self.assertIn("low", factor_data)
            self.assertIn("high", factor_data)
            
            # Alle Szenarien müssen relevante Felder enthalten
            for scenario in factor_data.values():
                self.assertIn("roi_months", scenario)
                self.assertIn("profit_yearly", scenario)

    def test_6_konkrete_handlungsempfehlungen(self):
        """Test: Konkrete Handlungsempfehlungen mit Priorisierung"""
        
        recommendations = ROIAnalyzer.generate_recommendations(
            budget=20000, 
            risk_tolerance="medium", 
            target_niche="medical"
        )
        
        # Muss mindestens eine Empfehlung geben
        self.assertIsInstance(recommendations, list)
        self.assertGreaterEqual(len(recommendations), 1)
        
        for rec in recommendations:
            self.assertIn("priority", rec)
            self.assertIn("config", rec)
            self.assertIn("break_even_months", rec)
            self.assertIn("roi_1_year", rec)
            
            # Priorität muss high/medium/low sein
            self.assertIn(rec["priority"], ["high", "medium", "low"])
            
            # Break-even Monate sinnvolle Range
            self.assertGreater(rec["break_even_months"], 0)

if __name__ == "__main__":
    unittest.main(verbosity=2)