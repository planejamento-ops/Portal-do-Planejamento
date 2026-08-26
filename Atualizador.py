import os
import json
import requests
import pandas as pd
from datetime import datetime, timedelta

# ==========================================
# 1. LINK DIRETO DO GOOGLE SHEETS
# ==========================================
link_download = "https://docs.google.com/spreadsheets/d/1MQ0zlahgcO6Y04dKfe2DQVnN_C0ReZL0kuOwv06-Iw8/export?format=csv&gid=0"

pasta_do_portal = os.path.dirname(os.path.abspath(__file__))

# ==========================================
# 2. JANELA DA SEMANA ATUAL (DOMINGO A SÁBADO)
# ==========================================
hoje = datetime.now()
dias_para_domingo = (hoje.weekday() + 1) % 7
data_inicio_semana = (hoje - timedelta(days=dias_para_domingo)).replace(hour=0, minute=0, second=0, microsecond=0)
data_fim_semana = data_inicio_semana + timedelta(days=6, hours=23, minutes=59, seconds=59)

print(f"🗓️ Data da Execução: {hoje.strftime('%d/%m/%Y %H:%M')}")

# ==========================================
# 3. DOWNLOAD DA PLANILHA
# ==========================================
print("1. Baixando dados diretamente do Google Sheets...")
res = requests.get(link_download)
caminho_csv = os.path.join(pasta_do_portal, "Controle_TU_Exportado.csv")
with open(caminho_csv, "wb") as f:
    f.write(res.content)

dados_google = pd.read_csv(caminho_csv, header=None, dtype=str).fillna("")

# LOCALIZA A LINHA EXATA DO CABEÇALHO
linha_cabecalho = 0
for indice, linha in dados_google.iterrows():
    valores_limpos = [str(v).strip().upper() for v in linha.values]
    if "TU" in valores_limpos or "DATA" in valores_limpos:
        linha_cabecalho = indice
        break

cols_map = {}
for c_i, c_v in enumerate(dados_google.iloc[linha_cabecalho].values):
    v_c = str(c_v).strip().upper()
    if v_c:
        cols_map[v_c] = c_i

df = dados_google.iloc[linha_cabecalho + 1:].copy().reset_index(drop=True)

# BUSCA MÚLTIPLAS VARIAÇÕES DE NOME PARA EVITAR KEYERROR
def busca_col_flexivel(termos):
    for t in termos:
        for k, v in cols_map.items():
            if t.upper() in k:
                return v
    return None

col_data_idx = busca_col_flexivel(["DATA", "DATE", "DT"])
col_tu_idx = busca_col_flexivel(["TU", "CODIGO TU", "CÓDIGO TU"])
col_carreta_idx = busca_col_flexivel(["CARRETA", "VEICULO", "PLACA"])
col_atend_idx = busca_col_flexivel(["ATENDIMENTO", "CANAL", "TIPO"])
col_uf_idx = busca_col_flexivel(["UF", "ESTADO", "DESTINO"])
col_status_idx = busca_col_flexivel(["STATUS", "SITUAÇÃO", "SITUACAO"])

col_cx_ln_idx = busca_col_flexivel(["LN CAIXAS", "LN CX", "CAIXAS LN"])
col_cx_gv_idx = busca_col_flexivel(["GV CAIXAS", "GV CX", "CAIXAS GV"])
col_pcs_ln_idx = busca_col_flexivel(["LN PEÇAS", "LN PCS", "PEÇAS LN", "PECAS LN"])
col_pcs_gv_idx = busca_col_flexivel(["GV PEÇAS", "GV PCS", "PEÇAS GV", "PECAS GV"])

# SE AINDA ASSIM NÃO ACHAR A DATA, DEFINE A COLUNA ZERO COMO PADRÃO SEGURA
if col_data_idx is None:
    col_data_idx = 0

if col_tu_idx is not None:
    df = df.dropna(subset=[col_tu_idx]).copy()
    df = df[df[col_tu_idx].astype(str).str.strip() != ""]

df['DATA_DT'] = pd.to_datetime(df[col_data_idx], format='mixed', errors='coerce')
df_semana = df[(df['DATA_DT'] >= data_inicio_semana) & (df['DATA_DT'] <= data_fim_semana)].copy()

def converter_inteiro_absoluto(col_idx):
    if col_idx is None or col_idx not in df_semana.columns:
        return pd.Series([0] * len(df_semana), index=df_semana.index, dtype=int)
    clean = df_semana[col_idx].astype(str).str.replace('\n', '', regex=False).str.replace('\r', '', regex=False)
    clean = clean.str.replace('.', '', regex=False).str.replace(',', '', regex=False)
    return pd.to_numeric(clean, errors='coerce').fillna(0).astype(int)

df_semana['LN_CX_NUM'] = converter_inteiro_absoluto(col_cx_ln_idx)
df_semana['GV_CX_NUM'] = converter_inteiro_absoluto(col_cx_gv_idx)
df_semana['LN_PCS_NUM'] = converter_inteiro_absoluto(col_pcs_ln_idx)
df_semana['GV_PCS_NUM'] = converter_inteiro_absoluto(col_pcs_gv_idx)

pendentes = pd.DataFrame()
if col_status_idx is not None and not df_semana.empty:
    pendentes = df_semana[df_semana[col_status_idx].astype(str).str.strip().str.upper() == 'NÃO INICIADO'].copy()

total_tus = len(df_semana)
qtd_carretas_pendentes = len(pendentes) if not pendentes.empty else 0

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
    "carretas_pendentes": qtd_carretas_pendentes,
    "progresso_pct": int(((total_tus - len(pendentes)) / total_tus * 100)) if total_tus > 0 else 100,
    "proxima_carteira": montar_info_fifo(pendentes, tipo_canal='CARTEIRA'),
    "proxima_varejo": montar_info_fifo(pendentes, tipo_canal='VAREJO'),
    "proxima_estojo": montar_info_fifo(pendentes, tipo_canal='ESTOJO'),
    "perfis": perfis_calculados
}

# 4. SALVA DADOS_TU.JS NA PASTA DO PROJETO
caminho_js = os.path.join(pasta_do_portal, "dados_tu.js")
with open(caminho_js, "w", encoding="utf-8") as f:
    f.write(f"const dadosDashboard = {json.dumps(dados_reais, ensure_ascii=False, indent=4)};")

print("✨ dados_tu.js gerado com sucesso!")