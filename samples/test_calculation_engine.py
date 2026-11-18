"""
Suíte de Testes Automatizados - Motor de Cálculo CLT e Portaria MTP nº 671/2021.
Validações de tolerâncias, cômputo integral, banco de horas e hora ficta noturna.

Execute na raiz do projeto:
    pytest samples/ -v
"""

import sys
from pathlib import Path

# Garante resolução tanto na raiz quanto dentro de samples/
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

SAMPLES_DIR = Path(__file__).resolve().parent
if str(SAMPLES_DIR) not in sys.path:
    sys.path.insert(0, str(SAMPLES_DIR))

import pytest
try:
    from samples.calculation_engine import CalculationEngine
except ImportError:
    from calculation_engine import CalculationEngine

def test_tolerancia_dentro_do_limite_clt():
    """
    Cenário: Batidas dentro da tolerância legal (Art. 58 § 1º CLT e Súmula 366 TST)
    - Previsto: 08:00 às 17:00 (480 min).
    - Marcações: 08:04 e 17:02 (desvios de 4 e 2 min, soma 6 <= 10 min).
    - Deve apurar a jornada prevista exata de 480 min, sem atraso e sem hora extra.
    """
    colaborador = {
        "jornada_diaria_minutos": 480,
        "horario_entrada": "08:00",
        "horario_saida": "17:00",
        "horario_saida_intervalo": "12:00",
        "horario_retorno_intervalo": "13:00",
        "banco_horas_ativo": 0
    }
    marcacoes = [
        "2026-10-15T08:04:00-03:00",
        "2026-10-15T17:02:00-03:00"
    ]
    res = CalculationEngine.apurar_dia(colaborador, "2026-10-15", marcacoes)

    assert res["total_previsto_minutos"] == 480
    assert res["total_trabalhado_minutos"] == 480
    assert res["horas_extras_50_minutos"] == 0
    assert res["atrasos_minutos"] == 0
    assert len(res["inconsistencias"]) == 0

def test_tolerancia_excedida_computo_integral_atraso():
    """
    Cenário: Desvio de marcação superior a 5 minutos (Súmula 366 TST).
    - Entrada 08:07 (desvio de 7 min > 5 min).
    - Não se deduzem os 5 minutos: o atraso é computado integralmente (7 min).
    """
    colaborador = {
        "jornada_diaria_minutos": 480,
        "horario_entrada": "08:00",
        "horario_saida": "17:00",
        "banco_horas_ativo": 0
    }
    marcacoes = [
        "2026-10-15T08:07:00-03:00",
        "2026-10-15T17:00:00-03:00"
    ]
    res = CalculationEngine.apurar_dia(colaborador, "2026-10-15", marcacoes)

    assert res["atrasos_minutos"] == 7
    assert res["total_trabalhado_minutos"] == 473
    assert res["horas_extras_50_minutos"] == 0

def test_tolerancia_excedida_horas_extras_integrais():
    """
    Cenário: Saída com mais de 5 minutos de acréscimo.
    - Saída 17:08 (8 min > 5 min).
    - Computa 8 minutos de hora extra 50% integralmente.
    """
    colaborador = {
        "jornada_diaria_minutos": 480,
        "horario_entrada": "08:00",
        "horario_saida": "17:00",
        "banco_horas_ativo": 0
    }
    marcacoes = [
        "2026-10-15T08:00:00-03:00",
        "2026-10-15T17:08:00-03:00"
    ]
    res = CalculationEngine.apurar_dia(colaborador, "2026-10-15", marcacoes)

    assert res["horas_extras_50_minutos"] == 8
    assert res["total_trabalhado_minutos"] == 488
    assert res["atrasos_minutos"] == 0

def test_banco_de_horas_ativo():
    """
    Cenário: Quando o colaborador possui banco de horas ativo,
    as horas excedentes são direcionadas para 'saldo_banco_minutos'.
    """
    colaborador = {
        "jornada_diaria_minutos": 480,
        "horario_entrada": "08:00",
        "horario_saida": "17:00",
        "banco_horas_ativo": 1
    }
    marcacoes = [
        "2026-10-15T08:00:00-03:00",
        "2026-10-15T18:00:00-03:00"  # +60 minutos
    ]
    res = CalculationEngine.apurar_dia(colaborador, "2026-10-15", marcacoes)

    assert res["saldo_banco_minutos"] == 60
    assert res["horas_extras_50_minutos"] == 0

def test_adicional_noturno_com_hora_ficta_reduzida():
    """
    Cenário: Jornada noturna urbana integral (22:00 às 05:00).
    - Tempo físico de relógio: 420 minutos (7 horas).
    - Fator de hora ficta CLT (60 / 52.5): 420 * 1.142857 = 480 minutos.
    - O adicional noturno apurado deve ser de 480 minutos.
    """
    colaborador = {
        "jornada_diaria_minutos": 420,
        "horario_entrada": "22:00",
        "horario_saida": "05:00",
        "banco_horas_ativo": 0
    }
    marcacoes = [
        "2026-10-10T22:00:00-03:00",
        "2026-10-11T05:00:00-03:00"
    ]
    res = CalculationEngine.apurar_dia(colaborador, "2026-10-10", marcacoes)

    assert res["adicional_noturno_minutos"] == 480
