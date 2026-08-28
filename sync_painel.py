import os
import json
import requests
import pandas as pd
from datetime import datetime, timedelta

link_download = "https://docs.google.com/spreadsheets/d/1MQ0zlahgcO6Y04dKfe2DQVnN_C0ReZL0kuOwv06-Iw8/export?format=csv&gid=0"

hoje = datetime.now()
dias_para_domingo = (hoje.weekday() + 1) % 7
data_inicio_semana = (hoje - timedelta(days=dias_para_domingo)).replace(hour=0, minute=0, second=0, microsecond=0)
data_fim_semana = data_inicio_semana + timedelta(days=6, hours=23, minutes=59, seconds=59)

res_csv = requests.get(link_download, timeout=30)
with open("Controle_TU_Exportado.csv", "wb") as f:
    f.write(res_csv.content)

df_raw = pd.read_csv("Controle_TU_Exportado.csv", header=None, dtype=str).fillna("")

linha_hdr = 0
for indice, linha in df_raw.iterrows():
    if "TU" in [str(v).strip().upper() for v in linha.values]:
        linha_hdr = indice
        break

cols_map = {str(c).strip().upper(): i for i, c in enumerate(df_raw.iloc[linha_hdr]) if str(c).strip()}
df = df_raw.iloc[linha_hdr + 1:].copy().reset_index(drop=True)

def busca_col(termo):
    for k, v in cols_map.items():
        if termo.upper() in k:
            return v
    return None

col_data_idx = busca_col("DATA")
col_tu_idx = busca_col("TU")
col_carreta_idx = busca_col("CARRETA")
col_atend_idx = busca_col("ATENDIMENTO")
col_uf_idx = busca_col("UF")
col_status_idx = busca_col("STATUS")
col_cx_ln_idx = busca_col("LN CAIXAS")
col_cx_gv_idx = busca_col("GV CAIXAS")
col_pcs_ln_idx = busca_col("LN PEÇAS")
col_pcs_gv_idx = busca_col("GV PEÇAS")

df = df[df[col_tu_idx].astype(str).str.strip() != ""].copy()
df['DATA_DT'] = pd.to_datetime(df[col_data_idx], format='mixed', errors='coerce')
df_semana = df[(df['DATA_DT'] >= data_inicio_semana) & (df['DATA_DT'] <= data_fim_semana)].copy()

def conv_num(series):
    if series is None:
        return pd.Series([], dtype=int)
    clean = series.astype(str).str.replace('\n', '').str.replace('\r', '').str.replace('.', '').str.replace(',', '')
    return pd.to_numeric(clean, errors='coerce').fillna(0).astype(int)

df_semana['LN_CX_NUM'] = conv_num(df_semana[col_cx_ln_idx])
df_semana['GV_CX_NUM'] = conv_num(df_semana[col_cx_gv_idx])
df_semana['LN_PCS_NUM'] = conv_num(df_semana[col_pcs_ln_idx])
df_semana['GV_PCS_NUM'] = conv_num(df_semana[col_pcs_gv_idx])

pendentes = df_semana[df_semana[col_status_idx].astype(str).str.strip().str.upper() == 'NÃO INICIADO'].copy() if col_status_idx is not None else pd.DataFrame()

def calc_perfil_especifico(df_base, filtro_atend, tipo_canal):
    if df_base.empty or col_atend_idx is None:
        return {"perfil": 0, "cx": 0, "pcs": 0}
    sub = df_base.copy()
    if filtro_atend:
        atend_upper = sub[col_atend_idx].astype(str).str.upper()
        sub = sub[atend_upper.str.contains(filtro_atend.upper(), na=False)]
    if sub.empty:
        return {"perfil": 0, "cx": 0, "pcs": 0}
    cx = int(sub['LN_CX_NUM'].sum()) if tipo_canal == "LN" else int(sub['GV_CX_NUM'].sum())
    pcs = int(sub['LN_PCS_NUM'].sum()) if tipo_canal == "LN" else int(sub['GV_PCS_NUM'].sum())
    return {"perfil": int(round(pcs / cx)) if cx > 0 else 0, "cx": cx, "pcs": pcs}

def montar_info_fifo(df_pend, eh_estojo=False):
    if df_pend.empty:
        return None
    sub = df_pend.copy()
    if col_atend_idx is not None:
        atend_str = sub[col_atend_idx].astype(str).str.upper()
        sub = sub[atend_str.str.contains('ESTOJO', na=False)] if eh_estojo else sub[~atend_str.str.contains('ESTOJO', na=False)]
    if sub.empty:
        return None
    p = sub.iloc[0]
    c_nome = str(p[col_carreta_idx]).replace('nan', '').strip()
    tu_cod = str(p[col_tu_idx]).replace('nan', '').replace('.0', '').strip()
    return {
        "carreta": f"{c_nome}" if 'Carreta' in c_nome else f"Carreta {c_nome}",
        "tu_resumida": f"...{tu_cod[-4:]}" if len(tu_cod) >= 4 else tu_cod,
        "uf": str(p[col_uf_idx]).replace('nan', '---') if col_uf_idx is not None else '---'
    }

dados_reais = {
    "atualizado_em": datetime.now().strftime("%d/%m/%Y %H:%M"),
    "total_tus": len(df_semana),
    "caixas_totais": int(df_semana['LN_CX_NUM'].sum() + df_semana['GV_CX_NUM'].sum()),
    "caixas_ln": int(df_semana['LN_CX_NUM'].sum()),
    "caixas_gv": int(df_semana['GV_CX_NUM'].sum()),
    "caixas_pendentes": int(pendentes['LN_CX_NUM'].sum() + pendentes['GV_CX_NUM'].sum()) if not pendentes.empty else 0,
    "caixas_ln_pend": int(pendentes['LN_CX_NUM'].sum()) if not pendentes.empty else 0,
    "caixas_gv_pend": int(pendentes['GV_CX_NUM'].sum()) if not pendentes.empty else 0,
    "pecas_totais": int(df_semana['LN_PCS_NUM'].sum() + df_semana['GV_PCS_NUM'].sum()),
    "pecas_ln": int(df_semana['LN_PCS_NUM'].sum()),
    "pecas_gv": int(df_semana['GV_PCS_NUM'].sum()),
    "pecas_pendentes": int(pendentes['LN_PCS_NUM'].sum() + pendentes['GV_PCS_NUM'].sum()) if not pendentes.empty else 0,
    "pecas_ln_pend": int(pendentes['LN_PCS_NUM'].sum()) if not pendentes.empty else 0,
    "pecas_gv_pend": int(pendentes['GV_PCS_NUM'].sum()) if not pendentes.empty else 0,
    "carretas_pendentes": pendentes[col_carreta_idx].nunique() if not pendentes.empty else 0,
    "progresso_pct": int(((len(df_semana) - len(pendentes)) / len(df_semana) * 100)) if len(df_semana) > 0 else 100,
    "proxima_carteira": montar_info_fifo(pendentes, eh_estojo=False),
    "proxima_estojo": montar_info_fifo(pendentes, eh_estojo=True),
    "pendencias_por_canal": {
        "varejo": len(pendentes[pendentes[col_atend_idx].astype(str).str.upper().str.contains("VAREJO", na=False)]) if not pendentes.empty else 0,
        "carteira": len(pendentes[pendentes[col_atend_idx].astype(str).str.upper().str.contains("CARTEIRA", na=False)]) if not pendentes.empty else 0,
        "estojo": len(pendentes[pendentes[col_atend_idx].astype(str).str.upper().str.contains("ESTOJO", na=False)]) if not pendentes.empty else 0
    },
    "perfis_geral": {
        "varejo_ln": calc_perfil_especifico(df_semana, "VAREJO", "LN"),
        "varejo_gv": calc_perfil_especifico(df_semana, "VAREJO", "GV"),
        "carteira_ln": calc_perfil_especifico(df_semana, "CARTEIRA", "LN"),
        "carteira_gv": calc_perfil_especifico(df_semana, "CARTEIRA", "GV"),
        "estojo_ln": calc_perfil_especifico(df_semana, "ESTOJO", "LN"),
        "estojo_gv": calc_perfil_especifico(df_semana, "ESTOJO", "GV"),
    },
    "perfis_pendentes": {
        "varejo_ln": calc_perfil_especifico(pendentes, "VAREJO", "LN"),
        "varejo_gv": calc_perfil_especifico(pendentes, "VAREJO", "GV"),
        "carteira_ln": calc_perfil_especifico(pendentes, "CARTEIRA", "LN"),
        "carteira_gv": calc_perfil_especifico(pendentes, "CARTEIRA", "GV"),
        "estojo_ln": calc_perfil_especifico(pendentes, "ESTOJO", "LN"),
        "estojo_gv": calc_perfil_especifico(pendentes, "ESTOJO", "GV"),
    }
}

conteudo_js = f"window.dadosDashboard = {json.dumps(dados_reais, ensure_ascii=False, indent=2)};"
with open("dados_tu.js", "w", encoding="utf-8") as f:
    f.write(conteudo_js)

print("dados_tu.js gerado com sucesso.")
