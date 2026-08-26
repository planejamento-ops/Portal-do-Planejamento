import os
import json
import requests
import pandas as pd
from datetime import datetime, timedelta

link_download = "https://docs.google.com/spreadsheets/d/1MQ0zlahgcO6Y04dKfe2DQVnN_C0ReZL0kuOwv06-Iw8/export?format=csv&gid=0"
pasta_do_portal = os.path.dirname(os.path.abspath(__file__))

# 1. JANELA DA SEMANA ATUAL
hoje = datetime.now()
dias_para_domingo = (hoje.weekday() + 1) % 7
data_inicio_semana = (hoje - timedelta(days=dias_para_domingo)).replace(hour=0, minute=0, second=0, microsecond=0)
data_fim_semana = data_inicio_semana + timedelta(days=6, hours=23, minutes=59, seconds=59)

print("1. Baixando planilha do Google Sheets...")
res = requests.get(link_download)
caminho_csv = os.path.join(pasta_do_portal, "Controle_TU_Exportado.csv")
with open(caminho_csv, "wb") as f:
    f.write(res.content)

# LÊ O CSV SEM PRECISAR LOCALIZAR CABEÇALHO POR NOME
dados_raw = pd.read_csv(caminho_csv, header=None, dtype=str).fillna("")

# LOCALIZA A PRIMEIRA LINHA ONDE APARECE O CÓDIGO DA TU OU A DATA
linha_inicio = 0
for idx, row in dados_raw.iterrows():
    vals = [str(v).strip().upper() for v in row.values]
    if "TU" in vals or "DATA" in vals:
        linha_inicio = idx + 1
        break

df = dados_raw.iloc[linha_inicio:].copy().reset_index(drop=True)

# MAPA FIXO DE COLUNAS DA SUPLIER (A=0, B=1, C=2...)
# Ajustado com base no padrão da base do Controle de TUs
COL_DATA = 0       # Coluna A
COL_TU = 1         # Coluna B
COL_CARRETA = 2    # Coluna C
COL_UF = 3         # Coluna D
COL_ATEND = 4      # Coluna E
COL_STATUS = 5     # Coluna F
COL_CX_LN = 6      # Coluna G (LN Caixas)
COL_PCS_LN = 7     # Coluna H (LN Peças)
COL_CX_GV = 8      # Coluna I (GV Caixas)
COL_PCS_GV = 9     # Coluna J (GV Peças)

# REMOVE LINHAS VAZIAS
df = df[df.iloc[:, COL_TU].astype(str).str.strip() != ""]

# TRATAMENTO DE DATA
df['DATA_DT'] = pd.to_datetime(df.iloc[:, COL_DATA], dayfirst=True, errors='coerce')
if df['DATA_DT'].isna().all():
    df['DATA_DT'] = pd.to_datetime(df.iloc[:, COL_DATA], format='mixed', errors='coerce')

# FILTRO DA SEMANA COM TRAVA DE SEGURANÇA
df_semana = df[(df['DATA_DT'] >= data_inicio_semana) & (df['DATA_DT'] <= data_fim_semana)].copy()

if df_semana.empty:
    print("⚠️ Filtro da semana sem registros. Carregando base total...")
    df_semana = df.copy()

# FUNÇÃO ROBUSTA DE LIMPEZA NUMÉRICA
def conv_num(col_idx):
    if col_idx >= df_semana.shape[1]:
        return pd.Series([0] * len(df_semana), index=df_semana.index, dtype=int)
    s = df_semana.iloc[:, col_idx].astype(str)
    s_limpo = s.str.replace('.', '', regex=False).str.replace(',', '', regex=False).str.extract(r'(\d+)')[0]
    return pd.to_numeric(s_limpo, errors='coerce').fillna(0).astype(int)

df_semana['LN_CX_NUM'] = conv_num(COL_CX_LN)
df_semana['GV_CX_NUM'] = conv_num(COL_CX_GV)
df_semana['LN_PCS_NUM'] = conv_num(COL_PCS_LN)
df_semana['GV_PCS_NUM'] = conv_num(COL_PCS_GV)

pendentes = df_semana[df_semana.iloc[:, COL_STATUS].astype(str).str.strip().str.upper().str.contains('NÃO INICIADO|NAO INICIADO|PENDENTE', regex=True, na=False)].copy()

total_tus = len(df_semana)

def calcular_perfil_direto(df_alvo, filtro_atend, canal):
    if df_alvo.empty: return 0.0
    sub = df_alvo.copy()
    if filtro_atend:
        sub = sub[sub.iloc[:, COL_ATEND].astype(str).str.upper().str.contains(filtro_atend.upper(), na=False)]
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
    if df_pend.empty: return None
    sub = df_pend.copy()
    atend_str = sub.iloc[:, COL_ATEND].astype(str).str.upper()
    
    if tipo_canal == 'ESTOJO': sub = sub[atend_str.str.contains('ESTOJO', na=False)]
    elif tipo_canal == 'CARTEIRA': sub = sub[atend_str.str.contains('CARTEIRA', na=False)]
    elif tipo_canal == 'VAREJO': sub = sub[atend_str.str.contains('VAREJO', na=False)]
    
    if sub.empty: return None
    p = sub.iloc[0]
    c_nome = str(p.iloc[COL_CARRETA]).replace('nan', '').strip()
    tu_cod = str(p.iloc[COL_TU]).replace('nan', '').replace('.0', '').strip()
    uf_val = str(p.iloc[COL_UF]).replace('nan', '---')
    
    tu_resumida = f"...{tu_cod[-5:]}" if len(tu_cod) >= 5 else tu_cod
    return {
        "carreta": f"{c_nome}" if 'Carreta' in c_nome.capitalize() else f"Carreta {c_nome}",
        "tu_resumida": tu_resumida,
        "uf": uf_val
    }

val_cx_ln_tot = int(df_semana['LN_CX_NUM'].sum())
val_cx_gv_tot = int(df_semana['GV_CX_NUM'].sum())
val_pcs_ln_tot = int(df_semana['LN_PCS_NUM'].sum())
val_pcs_gv_tot = int(df_semana['GV_PCS_NUM'].sum())

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

print(f"✨ Sucesso! {total_tus} TUs processadas no dados_tu.js")
