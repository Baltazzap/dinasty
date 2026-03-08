import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Button, View, Modal, TextInput
import os
from dotenv import load_dotenv

# Загрузка переменных из файла .env
load_dotenv()

# Получение токена из переменной DISCORD_TOKEN
TOKEN = os.getenv('DISCORD_TOKEN')

if not TOKEN:
    print("Ошибка: Токен не найден. Проверьте файл .env и переменную DISCORD_TOKEN")
    exit()

# --- КОНФИГУРАЦИЯ ID ---
# Категория для создания тикетов
CATEGORY_ID = 1449573036712919050
# Канал для логов (принято/отклонено)
LOG_CHANNEL_ID = 1449573243735511153
# Голосовой канал для собеседования
VOICE_CHANNEL_ID = 1449567766666416148

# Роли, которые могут использовать команду !заявка (ОБНОВЛЕНО)
COMMAND_ALLOWED_ROLES = [1449567765844459572]

# Роли, которые могут нажимать кнопки в тикете (Администрация)
TICKET_ADMIN_ROLES = [
    1449567765810778202,
    1449567765810778205,
    1449567765810778210
]

# --- НАСТРОЙКИ БОТА ---
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

# --- КЛАССЫ ИНТЕРФЕЙСА (UI) ---

class TicketButtons(View):
    """Кнопки внутри созданного тикета (Принять/Отклонить/Собес)"""
    def __init__(self, applicant: discord.Member):
        super().__init__(timeout=None)
        self.applicant = applicant

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Проверка: есть ли у нажавшего одна из админских ролей
        user_roles = [role.id for role in interaction.user.roles]
        if not any(role_id in user_roles for role_id in TICKET_ADMIN_ROLES):
            await interaction.response.send_message("У вас нет прав использовать эти кнопки.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Принять", style=discord.ButtonStyle.green, custom_id="accept_app")
    async def accept_callback(self, interaction: discord.Interaction, button: Button):
        # Логирование
        log_channel = interaction.guild.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            embed = discord.Embed(title="✅ Заявка ОДОБРЕНА", color=discord.Color.green())
            embed.add_field(name="Кандидат", value=self.applicant.mention)
            embed.add_field(name="Обработал", value=interaction.user.mention)
            await log_channel.send(embed=embed)
        
        await interaction.response.send_message("Заявка принята! Канал будет удален через 5 секунд.", ephemeral=True)
        await interaction.channel.delete(delay=5)

    @discord.ui.button(label="Отклонить", style=discord.ButtonStyle.red, custom_id="decline_app")
    async def decline_callback(self, interaction: discord.Interaction, button: Button):
        # Логирование
        log_channel = interaction.guild.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            embed = discord.Embed(title="❌ Заявка ОТКЛОНЕНА", color=discord.Color.red())
            embed.add_field(name="Кандидат", value=self.applicant.mention)
            embed.add_field(name="Обработал", value=interaction.user.mention)
            await log_channel.send(embed=embed)

        await interaction.response.send_message("Заявка отклонена! Канал будет удален через 5 секунд.", ephemeral=True)
        await interaction.channel.delete(delay=5)

    @discord.ui.button(label="Позвать на собес", style=discord.ButtonStyle.blurple, custom_id="interview_app")
    async def interview_callback(self, interaction: discord.Interaction, button: Button):
        voice_mention = f"<#{VOICE_CHANNEL_ID}>"
        await interaction.response.send_message(
            f"{self.applicant.mention}, Вас вызывают на собеседование! Зайдите в голосовой канал {voice_mention}",
            ephemeral=False
        )

class ApplicationModal(Modal, title="Анкета в семью"):
    """Форма заполнения заявки"""
    def __init__(self):
        super().__init__()
        
        # Поля формы
        self.nickname = TextInput(label="Ник в игре", placeholder="Ваш никнейм", max_length=50)
        self.static = TextInput(label="Статик", placeholder="Например: PC/Console", max_length=50)
        self.name_age = TextInput(label="Имя и возраст", placeholder="Иван, 20 лет", max_length=50)
        self.rp_exp = TextInput(label="Опыт на RP серверах", style=discord.TextStyle.long, max_length=1000)
        self.online = TextInput(label="Ежедневный онлайн", placeholder="Сколько часов в день", max_length=100)
        self.prev_families = TextInput(label="В каких семьях состояли до?", style=discord.TextStyle.long, max_length=1000, required=False)
        self.why_us = TextInput(label="Почему выбрали именно нас?", style=discord.TextStyle.long, max_length=1000)
        self.skills = TextInput(label="Ваши навыки стрельбы (Видео до 5 минут)", placeholder="Ссылка на видео", max_length=500, required=False)

        # Добавляем поля в модальное окно
        self.add_item(self.nickname)
        self.add_item(self.static)
        self.add_item(self.name_age)
        self.add_item(self.rp_exp)
        self.add_item(self.online)
        self.add_item(self.prev_families)
        self.add_item(self.why_us)
        self.add_item(self.skills)

    async def on_submit(self, interaction: discord.Interaction):
        # Создаем канал
        category = interaction.guild.get_channel(CATEGORY_ID)
        if not category:
            await interaction.response.send_message("Ошибка: Категория для заявок не найдена.", ephemeral=True)
            return

        channel_name = f"заявка-{interaction.user.name}"
        try:
            new_channel = await category.create_text_channel(
                name=channel_name,
                reason="Создание заявки в семью",
                topic=f"Заявка от {interaction.user.name}"
            )
            
            # Настраиваем права доступа (чтобы видел только автор и админы)
            await new_channel.set_permission(interaction.guild.default_role, view_channel=False)
            await new_channel.set_permission(interaction.user, view_channel=True, send_messages=True)
            
            # Добавляем права админ ролям (чтобы они могли зайти)
            for role_id in TICKET_ADMIN_ROLES:
                role = interaction.guild.get_role(role_id)
                if role:
                    await new_channel.set_permission(role, view_channel=True, send_messages=True)

            # Формируем эмбед с данными анкеты
            embed = discord.Embed(title=":file_folder: Новая заявка в семью", color=discord.Color.blue())
            embed.set_author(name=interaction.user.name, icon_url=interaction.user.avatar.url)
            embed.add_field(name=":bust_in_silhouette: Ник в игре", value=self.nickname.value, inline=True)
            embed.add_field(name=":game_die: Статик", value=self.static.value, inline=True)
            embed.add_field(name=":birthday: Имя и возраст", value=self.name_age.value, inline=True)
            embed.add_field(name=":book: Опыт RP", value=self.rp_exp.value, inline=False)
            embed.add_field(name=":clock: Онлайн", value=self.online.value, inline=True)
            embed.add_field(name=":family: Прошлые семьи", value=self.prev_families.value or "Не указано", inline=True)
            embed.add_field(name=":question: Почему мы?", value=self.why_us.value, inline=False)
            embed.add_field(name=":crossed_swords: Навыки (Видео)", value=self.skills.value or "Не предоставлено", inline=False)
            embed.set_footer(text=f"ID пользователя: {interaction.user.id}")

            # Отправляем сообщение в новый канал
            await new_channel.send(f"Заявка от {interaction.user.mention}", embed=embed, view=TicketButtons(interaction.user))
            
            await interaction.response.send_message(f"Ваша заявка отправлена! Проверьте канал {new_channel.mention}", ephemeral=True)

        except Exception as e:
            print(f"Ошибка создания канала: {e}")
            await interaction.response.send_message("Произошла ошибка при создании канала.", ephemeral=True)

class StartApplicationButton(View):
    """Кнопка на стартовом сообщении"""
    @discord.ui.button(label="Подать заявку в семью", style=discord.ButtonStyle.green, custom_id="start_app_btn")
    async def button_callback(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(ApplicationModal())

# --- КОМАНДЫ БОТА ---

@bot.command(name="заявка")
async def send_application_embed(ctx):
    # Проверка роли для использования команды
    user_roles = [role.id for role in ctx.author.roles]
    if not any(role_id in user_roles for role_id in COMMAND_ALLOWED_ROLES):
        await ctx.send("У вас нет доступа к этой команде.", ephemeral=True)
        return

    embed = discord.Embed(
        title=":hello: Путь в семью начинается здесь!",
        description=(
            "После заполнения анкеты Вам придет оповещение в ЛС от бота с результатом.\n"
            "Обычно заявки обрабатываются в течение 2–7 дней — всё зависит от того, "
            "насколько загружены наши рекрутеры на данный момент."
        ),
        color=discord.Color.gold()
    )
    
    view = StartApplicationButton()
    await ctx.send(embed=embed, view=view)

@bot.event
async def on_ready():
    print(f'Бот запущен как {bot.user}')

# Запуск бота
bot.run(TOKEN)
