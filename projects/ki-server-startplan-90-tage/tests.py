""" Tests fuer ki-server-startplan-90-tage - Evidence-Based Development. Jeder Test prueft ein Akzeptanzkriterium aus PLAN.md. Tests werden ZUERST geschrieben (Tests-First), dann Code. Projekt ist erst FERTIG wenn alle Tests PASS zeigen. """
import json
import os
from datetime import datetime, timedelta

def test_1_detaillierte_roi_rechnung_mit_allen_kost():
    """Kriterium: Detaillierte ROI-Rechnung mit allen Kosten und Einnahmen pro Szenario"""
    assert os.path.exists('roi_analysis.json'), "roi_analysis.json fehlt"
    with open('roi_analysis.json', 'r', encoding='utf-8') as f:
        roi_data = json.load(f)
    required_keys = ['konservativ', 'realistisch', 'optimistisch']
    for scenario in required_keys:
        assert scenario in roi_data, f"{scenario} Szenario fehlt"
        assert 'einnahmen' in roi_data[scenario], f"Einnahmen fehlen in {scenario}"
        assert 'kosten' in roi_data[scenario], f"Kosten fehlen in {scenario}"
        assert 'break_even_monate' in roi_data[scenario], f"Break-Even fehlt in {scenario}"
        assert isinstance(roi_data[scenario]['break_even_monate'], (int, float))

def test_2_konkrete_hardware_kaufliste_mit_genauen():
    """Kriterium: Konkrete Hardware-Kaufliste mit genauen Preisen und Lieferzeiten"""
    assert os.path.exists('hardware_liste.json'), "hardware_liste.json fehlt"
    with open('hardware_liste.json', 'r', encoding='utf-8') as f:
        hardware = json.load(f)
    assert 'gesamtpreis' in hardware, "Gesamtpreis fehlt"
    assert 'komponenten' in hardware, "Komponentenliste fehlt"
    assert len(hardware['komponenten']) > 0, "Keine Komponenten gelistet"
    for component in hardware['komponenten']:
        assert 'name' in component, "Komponentenname fehlt"
        assert 'preis' in component, "Preis fehlt"
        assert 'lieferzeit' in component, "Lieferzeit fehlt"
        assert isinstance(component['preis'], (int, float))
        assert component['preis'] > 0

def test_3_priorisierte_kundenliste_mit_10_potentie():
    """Kriterium: Priorisierte Kundenliste mit 10 potentiellen Erstkunden"""
    assert os.path.exists('kundenliste.json'), "kundenliste.json fehlt"
    with open('kundenliste.json', 'r', encoding='utf-8') as f:
        kunden = json.load(f)
    assert len(kunden) >= 10, f"Nur {len(kunden)} statt 10 Kunden gelistet"
    for kunde in kunden:
        assert 'name' in kunde, "Kundenname fehlt"
        assert 'branche' in kunde, "Branche fehlt"
        assert 'prioritaet' in kunde, "Prioritaet fehlt"
        assert 'kontakt' in kunde, "Kontaktinfo fehlt"
        assert kunde['prioritaet'] in ['Hoch', 'Mittel', 'Niedrig']

def test_4_woechentlicher_aktionsplan_fuer_die_ersten():
    """Kriterium: Woechentlicher Aktionsplan fuer die ersten 12 Wochen"""
    assert os.path.exists('aktionsplan.json'), "aktionsplan.json fehlt"
    with open('aktionsplan.json', 'r', encoding='utf-8') as f:
        plan = json.load(f)
    assert len(plan) == 12, f"{len(plan)} statt 12 Wochen geplant"
    for woche in plan:
        assert 'woche' in woche, "Wochennummer fehlt"
        assert 'ziele' in woche, "Ziele fehlen"
        assert 'aktionen' in woche, "Aktionen fehlen"
        assert len(woche['aktionen']) > 0, "Keine Aktionen definiert"

def test_5_risikoanalyse_mit_konkreten_gegenmassnahm():
    """Kriterium: Risikoanalyse mit konkreten Gegenmassnahmen"""
    assert os.path.exists('risikoanalyse.json'), "risikoanalyse.json fehlt"
    with open('risikoanalyse.json', 'r', encoding='utf-8') as f:
        risiko = json.load(f)
    assert len(risiko) >= 5, f"Nur {len(risiko)} statt mind. 5 Risiken analysiert"
    for risk in risiko:
        assert 'risiko' in risk, "Risikobeschreibung fehlt"
        assert 'wahrscheinlichkeit' in risk, "Wahrscheinlichkeit fehlt"
        assert 'auswirkung' in risk, "Auswirkung fehlt"
        assert 'gegenmassnahme' in risk, "Gegenmassnahme fehlt"
        assert risk['wahrscheinlichkeit'] in ['Niedrig', 'Mittel', 'Hoch']
        assert risk['auswirkung'] in ['Gering', 'Mittel', 'Hoch']

def test_6_skalierungsmodell_fuer_monat_4_12():
    """Kriterium: Skalierungsmodell fuer Monat 4-12"""
    assert os.path.exists('skalierungsmodell.json'), "skalierungsmodell.json fehlt"
    with open('skalierungsmodell.json', 'r', encoding='utf-8') as f:
        skalierung = json.load(f)
    assert 'monat_4_6' in skalierung, "Monat 4-6 fehlt"
    assert 'monat_7_9' in skalierung, "Monat 7-9 fehlt"
    assert 'monat_10_12' in skalierung, "Monat 10-12 fehlt"
    for phase in ['monat_4_6', 'monat_7_9', 'monat_10_12']:
        assert 'ziel_kunden' in skalierung[phase], "Ziel-Kunden fehlt"
        assert 'investition' in skalierung[phase], "Investition fehlt"
        assert 'strategie' in skalierung[phase], "Strategie fehlt"

def test_7_rechtliche_checkliste_fuer_dsgvo_konformi():
    """Kriterium: Rechtliche Checkliste fuer DSGVO-Konformitaet"""
    assert os.path.exists('dsgvo_checkliste.json'), "dsgvo_checkliste.json fehlt"
    with open('dsgvo_checkliste.json', 'r', encoding='utf-8') as f:
        checkliste = json.load(f)
    assert 'vertragsvorlagen' in checkliste, "Vertragsvorlagen fehlen"
    assert 'datenverarbeitung' in checkliste, "Datenverarbeitung fehlt"
    assert 'technische_massnahmen' in checkliste, "Technische Massnahmen fehlen"
    assert len(checkliste['vertragsvorlagen']) >= 3, "Min. 3 Vertragsvorlagen fehlen"
    assert len(checkliste['datenverarbeitung']) >= 5, "Min. 5 Datenverarbeitungspunkte fehlen"
    assert len(checkliste['technische_massnahmen']) >= 5, "Min. 5 technische Massnahmen fehlen"

# Tests ausfuehren
if __name__ == "__main__":
    tests = [
        test_1_detaillierte_roi_rechnung_mit_allen_kost,
        test_2_konkrete_hardware_kaufliste_mit_genauen,
        test_3_priorisierte_kundenliste_mit_10_potentie,
        test_4_woechentlicher_aktionsplan_fuer_die_ersten,
        test_5_risikoanalyse_mit_konkreten_gegenmassnahm,
        test_6_skalierungsmodell_fuer_monat_4_12,
        test_7_rechtliche_checkliste_fuer_dsgvo_konformi
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            print(f"PASS {test.__name__}")
            passed += 1
        except Exception as e:
            print(f"FAIL {test.__name__}: {e}")
            failed += 1
    
    print(f"\nErgebnis: {passed}/{len(tests)} Tests bestanden")
    if failed == 0:
        print("ALL_TESTS_PASSED")
    else:
        print(f"{failed} Tests fehlgeschlagen")