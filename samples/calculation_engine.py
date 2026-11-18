"""
Motor de Cálculo Trabalhista e Tratamento de Ponto (Amostra de Engenharia).
Compatível com as diretrizes da Portaria MTP nº 671/2021 e da CLT (Art. 58, 59, 71, 73 e Súmula 366 TST).

Autor: Victor Lacerda
Nota: Amostra higienizada e desacoplada de frameworks para fins de portfólio técnico.
"""

from datetime import datetime, timedelta, time, timezone
import math

class CalculationEngine:
    """
    Motor matemático puro de apuração de jornada.
    Totalmente determinístico, sem efeitos colaterais e sem acoplamento a ORM ou web frameworks.
    """

    TOLERANCIA_MAX_DIARIA_MINUTOS = 10
    TOLERANCIA_BATIDA_MINUTOS = 5
    FATOR_HORA_NOTURNA = 60.0 / 52.5  # ~1.142857 (Art. 73 § 1º da CLT: hora noturna de 52m30s)
    LIMITE_HE_DIARIA_MINUTOS = 120    # 2 horas diárias (Art. 59 CLT)
    FUSO_PADRAO = timezone(timedelta(hours=-3))

    @staticmethod
    def parse_iso_datetime(dt_str: str) -> datetime:
        """Normaliza strings ISO para datetime naive no fuso de apuração."""
        raw = dt_str.strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is not None:
            dt = dt.astimezone(CalculationEngine.FUSO_PADRAO).replace(tzinfo=None)
        return dt

    @staticmethod
    def minutos_entre(dt_inicio: datetime, dt_fim: datetime) -> int:
        """Calcula a diferença em minutos inteiros entre duas marcas temporais."""
        return int((dt_fim - dt_inicio).total_seconds() / 60)

    @staticmethod
    def obter_horarios_previstos(colaborador: dict, data_str: str) -> list:
        """Gera a lista de datetimes previstos para a escala contratual na data informada."""
        times_list = []
        if "horarios_previstos" in colaborador and colaborador["horarios_previstos"]:
            times_list = colaborador["horarios_previstos"]
        else:
            entrada = colaborador.get("horario_entrada")
            saida = colaborador.get("horario_saida")
            saida_int = colaborador.get("horario_saida_intervalo")
            retorno_int = colaborador.get("horario_retorno_intervalo")

            if entrada and saida:
                if saida_int and retorno_int:
                    times_list = [entrada, saida_int, retorno_int, saida]
                else:
                    times_list = [entrada, saida]

        dts = []
        base_date = datetime.strptime(data_str, "%Y-%m-%d")
        dia_offset = 0
        prev_t = None

        for item in times_list:
            if isinstance(item, datetime):
                dts.append(item)
                continue
            t_str = str(item)
            t_part = t_str.split("T")[-1][:5]
            h, m = map(int, t_part.split(":"))
            curr_t = time(h, m)
            if prev_t is not None and curr_t < prev_t:
                dia_offset += 1
            dts.append(base_date + timedelta(days=dia_offset, hours=h, minutes=m))
            prev_t = curr_t

        return dts

    @staticmethod
    def calcular_minutos_noturnos(
        dt_inicio: datetime,
        dt_fim: datetime,
        prorrogacao_com_hora_ficta: bool = False
    ) -> float:
        """
        Calcula os minutos trabalhados no período noturno urbano (22h às 05h)
        e aplica a redução ficta (52m30s convertida em 60m).
        """
        total_minutos_noturnos_reais = 0
        curr = dt_inicio
        step = timedelta(minutes=1)

        while curr < dt_fim:
            hora = curr.hour
            if hora >= 22 or hora < 5:
                total_minutos_noturnos_reais += 1
            curr += step

        minutos_noturnos_computados = total_minutos_noturnos_reais * CalculationEngine.FATOR_HORA_NOTURNA

        # Súmula 60, II do TST: Prorrogação após as 05:00
        iniciou_no_noturno = (dt_inicio.time() >= time(21, 55) or dt_inicio.time() <= time(5, 5))
        cumprida_integral = (iniciou_no_noturno and total_minutos_noturnos_reais >= 350)

        marco_05h = datetime(dt_inicio.year, dt_inicio.month, dt_inicio.day, 5, 0)
        if dt_inicio.hour >= 12:
            marco_05h += timedelta(days=1)

        if cumprida_integral and dt_fim > marco_05h:
            inicio_prorrogacao = max(dt_inicio, marco_05h)
            minutos_prorrogados = max(0, int((dt_fim - inicio_prorrogacao).total_seconds() / 60))
            if prorrogacao_com_hora_ficta:
                minutos_noturnos_computados += minutos_prorrogados * CalculationEngine.FATOR_HORA_NOTURNA
            else:
                minutos_noturnos_computados += minutos_prorrogados

        return minutos_noturnos_computados

    @staticmethod
    def extrair_batidas_dts(marcacoes_dia: list) -> list:
        """Extrai e ordena cronologicamente as marcações fornecidas."""
        batidas_dts = []
        for m in marcacoes_dia:
            if isinstance(m, str):
                dt = CalculationEngine.parse_iso_datetime(m)
            elif isinstance(m, dict):
                dt = CalculationEngine.parse_iso_datetime(m["data_hora_marcacao"])
            else:
                dt = m
            batidas_dts.append(dt)
        batidas_dts.sort()
        return batidas_dts

    @staticmethod
    def apurar_dia(colaborador: dict, data_str: str, marcacoes_dia: list) -> dict:
        """
        Apura a jornada diária consolidando:
        1. Tolerâncias CLT Art. 58 § 1º (5 min por batida e limite de 10 min diários);
        2. Cômputo integral caso a tolerância seja ultrapassada (Súmula 366 TST);
        3. Segregação de Horas Extras 50%/100% ou Banco de Horas;
        4. Adicional Noturno com hora ficta (CLT Art. 73).
        """
        batidas_dts = CalculationEngine.extrair_batidas_dts(marcacoes_dia)
        jornada_prevista_minutos = colaborador.get("jornada_diaria_minutos", 480)
        dt_dia = datetime.strptime(data_str, "%Y-%m-%d")
        eh_domingo = dt_dia.weekday() == 6
        inconsistencias = []

        marcacao_impar = (len(batidas_dts) % 2 != 0)
        if marcacao_impar:
            inconsistencias.append("MARCACAO_IMPAR: Registro incompleto para a jornada.")

        horarios_previstos = CalculationEngine.obter_horarios_previstos(colaborador, data_str)
        intervalo_previsto = 0
        if len(horarios_previstos) == 4:
            intervalo_previsto = CalculationEngine.minutos_entre(horarios_previstos[1], horarios_previstos[2])
        elif len(horarios_previstos) == 2 and jornada_prevista_minutos > 0:
            span_previsto = CalculationEngine.minutos_entre(horarios_previstos[0], horarios_previstos[1])
            if span_previsto > jornada_prevista_minutos:
                intervalo_previsto = span_previsto - jornada_prevista_minutos

        minutos_trabalhados = 0
        minutos_noturnos_computados = 0.0

        if len(batidas_dts) == 2 and intervalo_previsto > 0:
            entrada = batidas_dts[0]
            saida = batidas_dts[1]
            duracao_bruta = CalculationEngine.minutos_entre(entrada, saida)
            minutos_trabalhados = max(0, duracao_bruta - intervalo_previsto)
            minutos_noturnos_computados += CalculationEngine.calcular_minutos_noturnos(entrada, saida)
        else:
            i = 0
            while i + 1 < len(batidas_dts):
                entrada = batidas_dts[i]
                saida = batidas_dts[i+1]
                duracao = CalculationEngine.minutos_entre(entrada, saida)
                if duracao > 0:
                    minutos_trabalhados += duracao
                    minutos_noturnos_computados += CalculationEngine.calcular_minutos_noturnos(entrada, saida)
                i += 2

        # Aferição de Tolerância (CLT Art. 58 § 1º e Súmula 366 TST)
        tolerancia_batida = colaborador.get("tolerancia_batida_minutos", CalculationEngine.TOLERANCIA_BATIDA_MINUTOS)
        tolerancia_diaria = colaborador.get("tolerancia_diaria_minutos", CalculationEngine.TOLERANCIA_MAX_DIARIA_MINUTOS)

        desvios = []
        if len(horarios_previstos) > 0 and len(batidas_dts) > 0 and not marcacao_impar:
            if len(batidas_dts) == len(horarios_previstos):
                for b_dt, p_dt in zip(batidas_dts, horarios_previstos):
                    desvios.append(CalculationEngine.minutos_entre(p_dt, b_dt))
            elif len(batidas_dts) == 2 and len(horarios_previstos) >= 2:
                desvios.append(CalculationEngine.minutos_entre(horarios_previstos[0], batidas_dts[0]))
                desvios.append(CalculationEngine.minutos_entre(horarios_previstos[-1], batidas_dts[1]))
            else:
                desvios.append(minutos_trabalhados - jornada_prevista_minutos)
        elif len(batidas_dts) > 0 and not marcacao_impar:
            desvios.append(minutos_trabalhados - jornada_prevista_minutos)

        excedeu_batida = any(abs(d) > tolerancia_batida for d in desvios)
        soma_modulo_desvios = sum(abs(d) for d in desvios)
        excedeu_diario = soma_modulo_desvios > tolerancia_diaria

        dentro_tolerancia = (
            not marcacao_impar
            and not excedeu_batida
            and not excedeu_diario
            and jornada_prevista_minutos > 0
            and len(batidas_dts) > 0
        )

        horas_extras_50 = 0
        horas_extras_100 = 0
        atraso_minutos = 0

        if marcacao_impar:
            minutos_trabalhados_ajustados = minutos_trabalhados
            saldo_dia = 0
        elif dentro_tolerancia:
            # Tolerância atendida: apura a jornada prevista exata
            minutos_trabalhados_ajustados = jornada_prevista_minutos
            saldo_dia = 0
        else:
            # Tolerância quebrada: cômputo integral do desvio
            diferenca = minutos_trabalhados - jornada_prevista_minutos
            minutos_trabalhados_ajustados = minutos_trabalhados
            saldo_dia = diferenca

            if diferenca > 0:
                if eh_domingo:
                    horas_extras_100 = diferenca
                else:
                    horas_extras_50 = diferenca
            elif diferenca < 0:
                atraso_minutos = abs(diferenca)

        usa_banco = colaborador.get("banco_horas_ativo", 1)
        credito_banco = saldo_dia if (usa_banco and not marcacao_impar) else 0

        # Alerta legal se as horas extras do dia passarem de 2 horas (Art. 59 CLT)
        total_extras_dia = (horas_extras_50 + horas_extras_100) if not usa_banco else (saldo_dia if saldo_dia > 0 else 0)
        if total_extras_dia > CalculationEngine.LIMITE_HE_DIARIA_MINUTOS:
            inconsistencias.append(
                f"EXCESSO_HORAS_EXTRAS: {total_extras_dia} min extras excedem o limite diário de 2 horas (Art. 59 CLT)"
            )

        return {
            "data": data_str,
            "batidas": [dt.strftime("%H:%M") for dt in batidas_dts],
            "total_trabalhado_minutos": minutos_trabalhados_ajustados,
            "total_previsto_minutos": jornada_prevista_minutos,
            "horas_extras_50_minutos": horas_extras_50 if not usa_banco else 0,
            "horas_extras_100_minutos": horas_extras_100 if not usa_banco else 0,
            "adicional_noturno_minutos": int(round(minutos_noturnos_computados)),
            "atrasos_minutos": atraso_minutos if not usa_banco else 0,
            "saldo_banco_minutos": credito_banco,
            "eh_falta": (len(batidas_dts) == 0 and jornada_prevista_minutos > 0),
            "inconsistencias": inconsistencias
        }
