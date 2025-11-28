import os
import json
import calendar
from datetime import datetime
from typing import Dict, Any

import discord
from discord.ext import commands
from dotenv import load_dotenv

# ================== CONFIGURAÇÕES BÁSICAS ==================

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
CALENDAR_CHANNEL_ID = int(os.getenv("CALENDAR_CHANNEL_ID", "0"))

DATA_DIR = "data"
DATA_FILE = os.path.join(DATA_DIR, "ponto_data.json")

# Estrutura padrão do arquivo de dados
# {
#   "registros": {
#       "2025-11-28": {
#           "123456789012345678": {
#               "name": "usuario",
#               "entrada": "2025-11-28 09:00",
#               "saida": "2025-11-28 18:00"
#           }
#       },
#       ...
#   },
#   "mensagens": {
#       "2025-11": {
#           "message_id": 123456789012345678
#       }
#   }
# }

intents = discord.Intents.default()
intents.message_content = True  # necessário para comandos de texto

bot = commands.Bot(command_prefix="!", intents=intents)


# ================== FUNÇÕES DE PERSISTÊNCIA ==================

def garantir_arquivo():
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump({"registros": {}, "mensagens": {}}, f, ensure_ascii=False, indent=2)


def carregar_dados() -> Dict[str, Any]:
    garantir_arquivo()
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def salvar_dados(dados: Dict[str, Any]) -> None:
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)


def get_month_key(dt: datetime) -> str:
    return dt.strftime("%Y-%m")


def get_date_str(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


# ================== FUNÇÃO DE RENDERIZAÇÃO DO CALENDÁRIO ==================

MESES_PT = {
    1: "Janeiro",
    2: "Fevereiro",
    3: "Março",
    4: "Abril",
    5: "Maio",
    6: "Junho",
    7: "Julho",
    8: "Agosto",
    9: "Setembro",
    10: "Outubro",
    11: "Novembro",
    12: "Dezembro",
}


def renderizar_calendario(year: int, month: int, registros: Dict[str, Any]) -> str:
    """
    Gera texto do calendário + lista de registros por dia.
    """
    cal = calendar.Calendar(firstweekday=0)  # Monday
    month_key = f"{year:04d}-{month:02d}"

    # 1) Grade do calendário (visual)
    linhas = []
    linhas.append("```")
    linhas.append("Seg Ter Qua Qui Sex Sáb Dom")

    # monthdayscalendar devolve semanas começando em Monday
    for week in cal.monthdayscalendar(year, month):
        linha_semana = []
        # week = [seg, ter, qua, qui, sex, sab, dom]
        for day in week:
            if day == 0:
                linha_semana.append("   ")
            else:
                linha_semana.append(f"{day:2d} ")
        linhas.append(" ".join(linha_semana))
    linhas.append("```")

    # 2) Detalhes de ponto por dia
    registros_mes = {}
    for data_str, usuarios in registros.items():
        if data_str.startswith(month_key):
            registros_mes[data_str] = usuarios

    if not registros_mes:
        linhas.append("_Ainda não há registros de ponto neste mês._")
        return "\n".join(linhas)

    linhas.append("**Registros de ponto por dia:**")
    # Ordena os dias
    for data_str in sorted(registros_mes.keys()):
        dt = datetime.strptime(data_str, "%Y-%m-%d")
        dia = dt.day
        linhas.append(f"\n__Dia {dia:02d}/{month:02d}__")
        usuarios = registros_mes[data_str]
        for user_id, info in usuarios.items():
            nome = info.get("name", str(user_id))
            entrada = info.get("entrada", "--:--")
            saida = info.get("saida", "--:--")
            # Pega só HH:MM
            if entrada != "--:--" and " " in entrada:
                entrada = entrada.split(" ")[1][:5]
            if saida != "--:--" and " " in saida:
                saida = saida.split(" ")[1][:5]
            linhas.append(f"- {nome}: entrada {entrada} | saída {saida}")

    return "\n".join(linhas)


async def atualizar_mensagem_calendario(
    client: discord.Client,
    year: int,
    month: int,
):
    """
    Gera/atualiza a mensagem de calendário do mês (um por mês),
    no canal configurado em CALENDAR_CHANNEL_ID.
    """
    if CALENDAR_CHANNEL_ID == 0:
        print("CALENDAR_CHANNEL_ID não configurado no .env.")
        return

    dados = carregar_dados()
    registros = dados.get("registros", {})
    mensagens = dados.get("mensagens", {})

    month_key = f"{year:04d}-{month:02d}"
    canal = client.get_channel(CALENDAR_CHANNEL_ID)
    if canal is None:
        canal = await client.fetch_channel(CALENDAR_CHANNEL_ID)

    # Renderiza texto do calendário
    descricao = renderizar_calendario(year, month, registros)
    titulo = f"Calendário de ponto - {MESES_PT[month]}/{year}"

    # Já existe mensagem fixa para este mês?
    message_info = mensagens.get(month_key)
    if message_info:
        message_id = message_info.get("message_id")
        try:
            msg = await canal.fetch_message(message_id)
            await msg.edit(content=None, embed=discord.Embed(title=titulo, description=descricao))
            return
        except discord.NotFound:
            # mensagem sumiu, vamos recriar
            pass

    # Não há mensagem registrada ou sumiu: cria nova
    embed = discord.Embed(title=titulo, description=descricao)
    msg = await canal.send(embed=embed)

    # salva o ID da nova mensagem
    mensagens[month_key] = {"message_id": msg.id}
    dados["mensagens"] = mensagens
    salvar_dados(dados)


# ================== VIEW COM BOTÕES ==================

class PontoView(discord.ui.View):
    def __init__(self, timeout: float | None = None):
        super().__init__(timeout=timeout)

    @discord.ui.button(label="ENTRADA", style=discord.ButtonStyle.success)
    async def botao_entrada(self, interaction: discord.Interaction, button: discord.ui.Button):
        await registrar_ponto(interaction, tipo="entrada")

    @discord.ui.button(label="SAÍDA", style=discord.ButtonStyle.danger)
    async def botao_saida(self, interaction: discord.Interaction, button: discord.ui.Button):
        await registrar_ponto(interaction, tipo="saida")


# ================== LÓGICA DE REGISTRO ==================

async def registrar_ponto(interaction: discord.Interaction, tipo: str):
    agora = datetime.now()
    date_str = get_date_str(agora)      # "YYYY-MM-DD"
    hora_str = agora.strftime("%Y-%m-%d %H:%M")

    dados = carregar_dados()
    registros = dados.get("registros", {})

    user_id = str(interaction.user.id)
    nome = interaction.user.display_name

    if date_str not in registros:
        registros[date_str] = {}
    if user_id not in registros[date_str]:
        registros[date_str][user_id] = {
            "name": nome,
            "entrada": "--:--",
            "saida": "--:--",
        }

    if tipo == "entrada":
        registros[date_str][user_id]["entrada"] = hora_str
        msg_conf = f"Entrada registrada para {nome} às **{hora_str[11:16]}**."
    else:
        registros[date_str][user_id]["saida"] = hora_str
        msg_conf = f"Saída registrada para {nome} às **{hora_str[11:16]}**."

    dados["registros"] = registros
    salvar_dados(dados)

    # Atualiza o calendário do mês atual no canal fixo
    await atualizar_mensagem_calendario(interaction.client, year=agora.year, month=agora.month)

    # Responde ao usuário (mensagem efêmera só pra quem clicou)
    await interaction.response.send_message(msg_conf, ephemeral=True)


# ================== EVENTOS E COMANDOS ==================

@bot.event
async def on_ready():
    print(f"Bot conectado como {bot.user} (ID: {bot.user.id})")
    garantir_arquivo()


@bot.command(name="ponto")
async def comando_ponto(ctx: commands.Context):
    """
    Envia uma mensagem com os botões de ENTRADA e SAÍDA.
    Você pode usar esse comando no canal que quiser e fixar a mensagem.
    """
    view = PontoView()
    await ctx.send("Controle de ponto - clique em **ENTRADA** ou **SAÍDA**:", view=view)


@bot.command(name="atualizar_calendario")
@commands.has_permissions(administrator=True)
async def comando_atualizar_calendario(ctx: commands.Context, ano: int | None = None, mes: int | None = None):
    """
    Comando opcional para forçar atualização manual do calendário do mês
    no canal configurado em CALENDAR_CHANNEL_ID.
    Exemplo: !atualizar_calendario 2025 11
    Se não passar nada, usa mês atual.
    """
    agora = datetime.now()
    if ano is None:
        ano = agora.year
    if mes is None:
        mes = agora.month

    await atualizar_mensagem_calendario(ctx.bot, ano, mes)
    await ctx.send(f"Calendário de {MESES_PT[mes]}/{ano} atualizado.", delete_after=10)


@bot.command(name="calendario")
async def comando_calendario(ctx: commands.Context, ano: int, mes: int):
    """
    Consulta qualquer mês/ano (passado ou futuro) e mostra o calendário
    com os registros armazenados.
    Exemplo: !calendario 2024 5
    """
    if mes < 1 or mes > 12:
        await ctx.send("Mês inválido. Use um valor entre 1 e 12. Ex.: `!calendario 2024 5`")
        return

    dados = carregar_dados()
    registros = dados.get("registros", {})

    descricao = renderizar_calendario(ano, mes, registros)
    titulo = f"Calendário de ponto - {MESES_PT[mes]}/{ano}"
    embed = discord.Embed(title=titulo, description=descricao)

    await ctx.send(embed=embed)


# ================== MAIN ==================

if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError("DISCORD_TOKEN não foi definido no .env ou nas variáveis de ambiente")
    bot.run(TOKEN)
