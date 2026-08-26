import os
import json
import requests
import pandas as pd
from datetime import datetime, timedelta

link_download = "https://docs.google.com/spreadsheets/d/1MQ0zlahgcO6Y04dKfe2DQVnN_C0ReZL0kuOwv06-Iw8/export?format=csv&gid=0"
pasta_do_portal = os.path.dirname(os.path.abspath(__file__))

# 1. JANELA DA SEMANA
hoje = datetime.now()
dias_para_domingo = (hoje.weekday() + 1) % 7
data_inicio_semana = (hoje - timedelta(days=dias_para_domingo)).replace(hour=0, minute=0, second=0, microsecond=0)
data_fim_semana = data_inicio_semana + timedelta(days=6, hours=23, minutes=59, seconds=59)

print(f"🗓️ Filtrando semana de {data_inicio_semana.strftime('%d/%m/%Y')} a {data_fim_semana.strftime('%d/%m/%Y')}")

# 2. DOWNLOAD E LEITURA
res = requests.get(link_download)
caminho_csv = os.path.join(pasta_do_portal, "Controle_TU_Exportado.csv")
with open(caminho_csv, "wb") as f:
    f.write(res.content)

dados_raw = pd.read_csv(caminho_csv, header=None, dtype=str).fillna("")

linha_cabecalho = 0
for idx, row in dados_raw.iterrows():
    vals = [str(v).strip().upper() for v in row.values]
    if "TU" in vals or "DATA" in vals:
        linha_cabecalho = idx
        break

cols_map = {}
for c_i, c_v in enumerate(dados_raw.iloc[linha_cabecalho].values):
    v_c = str(c_v).strip().upper()
    if v_c: cols_map[v_c] = c_i

df = dados_raw.iloc[linha_cabecalho + 1:].copy().reset_index(drop=True)

def pega_col_idx(termo):
    for k, v in cols_map.items():
        if termo.upper() in k: return v
    return None

col_data_idx = pega_col_idx("DATA")
col_tu_idx = pega_col_idx("TU")
col_carreta_idx = pega_col_idx("CARRETA")
col_atend_idx = pega_col_idx("ATENDIMENTO")
col_uf_idx = pega_col_idx("UF")
col_status_idx = pega_col_idx("STATUS")

col_cx_ln_idx = pega_col_idx("LN CAIXAS")
col_cx_gv_idx = pega_col_idx("GV CAIXAS")
col_pcs_ln_idx = pega_col_idx("LN PEÇAS")
col_pcs_gv_idx = pega_col_idx("GV PEÇAS")

# REMOVE LINHAS SEM TU
if col_tu_idx is not None:
    df = df[df[col_tu_idx].astype(str).str.strip() != ""]

# 3. TRATAMENTO DE DATA BRASILEIRA
if col_data_idx is not None:
    df['DATA_DT'] = pd.to_datetime(df[col_data_idx], dayfirst=True, errors='coerce')
    # Se todas ficarem nulas pelo dayfirst, tenta a conversão automática genérica
    if df['DATA_DT'].isna().all():
        df['DATA_DT'] = pd.to_datetime(df[col_data_idx], format='mixed', errors='coerce')
else:
    df['DATA_DT'] = pd.NaT

# FILTRA A SEMANA OU PEGA O REPOSITÓRIO COMPLETO SE A DATA VIER NULA
df_semana = df[(df['DATA_DT'] >= data_inicio_semana) & (df['DATA_DT'] <= data_fim_semana)].copy()

if df_semana.empty:
    print("⚠️ Nenhuma TU encontrada estritamente na data da semana. Carregando base geral disponível...")
    df_semana = df.copy()

def conv_num(col_idx):
    if col_idx is None or df_semana.empty or col_idx not in df_semana.columns:
        return pd.Series([0] * len(df_semana), index=df_semana.index, dtype=int)
    s = df_semana[col_idx].astype(str).str.replace('.', '', regex=False).str.replace(',', '', regex=False)
    return pd.to_numeric(s, errors='coerce').fillna(0).astype(int)

df_semana['LN_CX_NUM'] = conv_num(col_cx_ln_idx)
df_semana['GV_CX_NUM'] = conv_num(col_cx_gv_idx)
df_semana['LN_PCS_NUM'] = conv_num(col_pcs_ln_idx)
df_semana['GV_PCS_NUM'] = conv_num(col_pcs_gv_idx)

pendentes = pd.DataFrame()
if col_status_idx is not None and not df_semana.empty:
    pendentes = df_semana[df_semana[col_status_idx].astype(str).str.strip().str.upper().str.contains('NÃO INICIADO|NAO INICIADO|PENDENTE', regex=True, na=False)].copy()

total_tus = len(df_semana)

def calcular_perfil_direto(df_alvo, filtro_atend, canal):
    if df_alvo.empty: return 0.0
    sub = df_alvo.copy()
    if filtro_atend and col_atend_idx is not None:
        sub = sub[sub[col_atend_idx].astype(str).str.upper().str.contains(filtro_atend.upper(), na=False)]
    if sub.empty: return 0.0
    
    if canal == 'VAREJO_LN':
        cx = sub['LN_CX_NUM'].sum()
        pcs = sub['LN_PCS_NUM'].sum()
    elif canal == 'VAREJO_GV':
        cx = sub['GV_CX_NUM'].sum()
        pcs = sub['GV_PCS_NUM'].sum()
    else:
        cx = sub['LN_CX_NUM'].sum() + sub['GV_CX_NUM'].sum()
        pcs = sub['LN_PCS_NUM'].sum() + sub['GV_PCS_NUM'].sum()
        
    return round(pcs / cx, 1) if cx > 0 else 0.0

perfis_calculados = {
    "varejo_ln_pend": calcular_perfil_direto(pendentes, 'VAREJO', 'VAREJO_LN'),
    "varejo_ln_tot": calcular_perfil_direto(df_semana, 'VAREJO', 'VAREJO_LN'),
    "varejo_gv_pend": calcular_perfil_direto(pendentes, 'VAREJO', 'VAREJO_GV'),
    "varejo_gv_tot": calcular_perfil_direto(df_semana, 'VAREJO', 'VAREJO_GV'),
    "carteira_pend": calcular_perfil_direto(pendentes, 'CARTEIRA', 'CARTEIRA'),
    "carteira_tot": calcular_perfil_direto(df_semana, 'CARTEIRA', 'CARTEIRA'),
    "estojo_pend": calcular_perfil_direto(pendentes, 'ESTOJO', 'ESTOJO'),
    "estojo_tot": calcular_perfil_direto(df_semana, 'ESTOJO', 'ESTOJO'),
}

def montar_info_fifo(df_pend, tipo_canal):
    if df_pend.empty or col_carreta_idx is None or col_tu_idx is None: return None
    sub = df_pend.copy()
    if col_atend_idx is not None:
        atend_str = sub[col_atend_idx].astype(str).str.upper()
        if tipo_canal == 'ESTOJO': sub = sub[atend_str.str.contains('ESTOJO', na=False)]
        elif tipo_canal == 'CARTEIRA': sub = sub[atend_str.str.contains('CARTEIRA', na=False)]
        elif tipo_canal == 'VAREJO': sub = sub[atend_str.str.contains('VAREJO', na=False)]
    
    if sub.empty: return None
    p = sub.iloc[0]
    c_nome = str(p[col_carreta_idx]).replace('nan', '').strip()
    tu_cod = str(p[col_tu_idx]).replace('nan', '').replace('.0', '').strip()
    uf_val = str(p[col_uf_idx]).replace('nan', '---') if col_uf_idx is not None else '---'
    
    tu_resumida = f"...{tu_cod[-5:]}" if len(tu_cod) >= 5 else tu_cod
    return {
        "carreta": f"{c_nome}" if 'Carreta' in c_nome.capitalize() else f"Carreta {c_nome}",
        "tu_resumida": tu_resumida,
        "uf": uf_val
    }

val_cx_ln_tot = int(df_semana['LN_CX_NUM'].sum()) if not df_semana.empty else 0
val_cx_gv_tot = int(df_semana['GV_CX_NUM'].sum()) if not df_semana.empty else 0
val_pcs_ln_tot = int(df_semana['LN_PCS_NUM'].sum()) if not df_semana.empty else 0
val_pcs_gv_tot = int(df_semana['GV_PCS_NUM'].sum()) if not df_semana.empty else 0

val_cx_ln_pend = int(pendentes['LN_CX_NUM'].sum()) if not pendentes.empty else 0
val_cx_gv_pend = int(pendentes['GV_CX_NUM'].sum()) if not pendentes.empty else 0
val_pcs_ln_pend = int(pendentes['LN_PCS_NUM'].sum()) if not pendentes.empty else 0
val_pcs_gv_pend = int(pendentes['GV_PCS_NUM'].sum()) if not pendentes.empty else 0

dados_reais = {
    "atualizado_em": datetime.now().strftime("%d/%m/%Y %H:%M"),
    "total_tus": total_tus,
    "caixas_totais": val_cx_ln_tot + val_cx_gv_tot,
    "caixas_ln": val_cx_ln_tot,
    "caixas_gv": val_cx_gv_tot,
    "caixas_pendentes": val_cx_ln_pend + val_cx_gv_pend,
    "caixas_ln_pend": val_cx_ln_pend,
    "caixas_gv_pend": val_cx_gv_pend,
    "pecas_totais": val_pcs_ln_tot + val_pcs_gv_tot,
    "pecas_ln": val_pcs_ln_tot,
    "pecas_gv": val_pcs_gv_tot,
    "pecas_pendentes": val_pcs_ln_pend + val_pcs_gv_pend,
    "pecas_ln_pend": val_pcs_ln_pend,
    "pecas_gv_pend": val_pcs_gv_pend,
    "carretas_pendentes": len(pendentes),
    "progresso_pct": int(((total_tus - len(pendentes)) / total_tus * 100)) if total_tus > 0 else 100,
    "proxima_carteira": montar_info_fifo(pendentes, tipo_canal='CARTEIRA'),
    "proxima_varejo": montar_info_fifo(pendentes, tipo_canal='VAREJO'),
    "proxima_estojo": montar_info_fifo(pendentes, tipo_canal='ESTOJO'),
    "perfis": perfis_calculados
}

caminho_js = os.path.join(pasta_do_portal, "dados_tu.js")
with open(caminho_js, "w", encoding="utf-8") as f:
    f.write(f"const dadosDashboard = {json.dumps(dados_reais, ensure_ascii=False, indent=4)};")

print(f"✨ Sucesso! {total_tus} TUs processadas para o Portal.")
