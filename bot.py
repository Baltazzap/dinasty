import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Button, View, Modal, TextInput
import os
import traceback
import asyncio

# Получение токена из переменной окружения DISCORD_TOKEN
TOKEN = os.getenv('DISCORD_TOKEN')

if not TOKEN:
    print("Ошибка: Токен не найден. Проверьте переменную окружения DISCORD_TOKEN")
    exit()

# --- КОНФИГУРАЦИЯ ID ---
CATEGORY_ID = 1451275518740791326
LOG_CHANNEL_ID = 1449573243735511153
VOICE_CHANNEL_ID = 1449567766666416148

# Роль для упоминания при новой заявке
NOTIFY_ROLE_ID = 1449567765810778202

# 🛡️ ID владельца бота (имеет полный доступ ко всем функциям)
OWNER_ID = 314805583788244993

COMMAND_ALLOWED_ROLES = [1449567765844459572]

# Роли, которые могут нажимать кнопки в тикете (Администрация)
TICKET_ADMIN_ROLES = [
    1449567765810778202,
    1449567765810778205,
    1449567765810778210,
    1449567765810778211
]

# 🛠️ Роли, которые могут использовать команду !rename
RENAME_ALLOWED_ROLES = [
    1449567765810778202,
    1449567765810778205,
    1449567765810778210,
    1449567765810778211
]

# 🎭 Роли для управления при принятии заявки
ROLE_ADD_1 = 1449567765798191154
ROLE_ADD_2 = 1449575866630934640
ROLE_REMOVE = 1449575999850418308

# --- НАСТРОЙКИ БОТА ---
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

# --- КЛАССЫ ИНТЕРФЕЙСА (UI) ---

class DeclineReasonModal(Modal, title="Причина отклонения"):
    def __init__(self, applicant: discord.Member, application_embed: discord.Embed, interaction: discord.Interaction):
        super().__init__()
        self.applicant = applicant
        self.application_embed = application_embed
        self.original_interaction = interaction
        
        self.reason_input = TextInput(
            label="Укажите причину отклонения",
            placeholder="Например: Не подходит по возрасту / Мало опыта / Не заполнены поля",
            style=discord.TextStyle.long,
            max_length=500,
            required=True
        )
        self.add_item(self.reason_input)

    async def on_submit(self, interaction: discord.Interaction):
        await self.send_to_logs_with_reason(interaction, self.reason_input.value)

    async def send_to_logs_with_reason(self, interaction: discord.Interaction, reason: str):
        log_channel = interaction.guild.get_channel(LOG_CHANNEL_ID)
        if not log_channel:
            return

        log_embed = discord.Embed(
            title="❌ Заявка ОТКЛОНЕНА",
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow()
        )
        
        log_embed.add_field(name="👤 Кандидат", value=self.applicant.mention, inline=True)
        log_embed.add_field(name="🔨 Обработал", value=interaction.user.mention, inline=True)
        log_embed.add_field(name="📝 Причина отказа", value=reason, inline=False)
        log_embed.add_field(name="⠀", value="━━━━━━━━━━━━━━━━━━━━", inline=False)
        
        if self.application_embed.fields:
            for field in self.application_embed.fields:
                log_embed.add_field(name=field.name, value=field.value, inline=field.inline)
        
        log_embed.set_footer(text=f"ID пользователя: {self.applicant.id}")
        if self.application_embed.author:
            log_embed.set_author(name=self.application_embed.author.name, icon_url=self.application_embed.author.icon_url)

        await log_channel.send(embed=log_embed)
        
        try:
            await self.applicant.send(
                f"❌ Ваша заявка в семью была отклонена.\n"
                f"📝 **Причина:** {reason}\n"
                f"Вы можете подать новую заявку через некоторое время, если исправите указанные недостатки."
            )
        except:
            pass

        await self.original_interaction.followup.send("Заявка отклонена! Канал будет удален через 5 секунд.", ephemeral=True)
        await asyncio.sleep(5)
        await interaction.channel.delete()


class TicketButtons(View):
    def __init__(self, applicant: discord.Member, application_embed: discord.Embed):
        super().__init__(timeout=None)
        self.applicant = applicant
        self.application_embed = application_embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == OWNER_ID:
            return True
        
        user_roles = [role.id for role in interaction.user.roles]
        if not any(role_id in user_roles for role_id in TICKET_ADMIN_ROLES):
            await interaction.response.send_message("У вас нет прав использовать эти кнопки.", ephemeral=True)
            return False
        return True

    async def send_to_logs(self, interaction: discord.Interaction, status: str, color: discord.Color):
        log_channel = interaction.guild.get_channel(LOG_CHANNEL_ID)
        if not log_channel:
            return

        log_embed = discord.Embed(
            title=f"{status}",
            color=color,
            timestamp=discord.utils.utcnow()
        )
        
        log_embed.add_field(name="👤 Кандидат", value=self.applicant.mention, inline=True)
        log_embed.add_field(name="🔨 Обработал", value=interaction.user.mention, inline=True)
        log_embed.add_field(name="⠀", value="━━━━━━━━━━━━━━━━━━━━", inline=False)
        
        if self.application_embed.fields:
            for field in self.application_embed.fields:
                log_embed.add_field(name=field.name, value=field.value, inline=field.inline)
        
        log_embed.set_footer(text=f"ID пользователя: {self.applicant.id}")
        if self.application_embed.author:
            log_embed.set_author(name=self.application_embed.author.name, icon_url=self.application_embed.author.icon_url)

        await log_channel.send(embed=log_embed)

    @discord.ui.button(label="Принять", style=discord.ButtonStyle.green, custom_id="accept_app")
    async def accept_callback(self, interaction: discord.Interaction, button: Button):
        try:
            await self.send_to_logs(interaction, "✅ Заявка ОДОБРЕНА", discord.Color.green())
            
            try:
                role1 = interaction.guild.get_role(ROLE_ADD_1)
                role2 = interaction.guild.get_role(ROLE_ADD_2)
                
                if role1:
                    await self.applicant.add_roles(role1, reason="Заявка в семью одобрена")
                if role2:
                    await self.applicant.add_roles(role2, reason="Заявка в семью одобрена")
                
                role_remove = interaction.guild.get_role(ROLE_REMOVE)
                if role_remove:
                    await self.applicant.remove_roles(role_remove, reason="Заявка в семью одобрена")
            except Exception as e:
                print(f"Ошибка при управлении ролями: {e}")
            
            await interaction.response.send_message("Заявка принята! Роли выданы. Канал будет удален через 5 секунд.", ephemeral=True)
            await asyncio.sleep(5)
            await interaction.channel.delete()
        except Exception as e:
            print(f"Ошибка в accept_callback: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message("Произошла ошибка при обработке.", ephemeral=True)

    @discord.ui.button(label="Отклонить", style=discord.ButtonStyle.red, custom_id="decline_app")
    async def decline_callback(self, interaction: discord.Interaction, button: Button):
        try:
            await interaction.response.send_modal(
                DeclineReasonModal(self.applicant, self.application_embed, interaction)
            )
        except Exception as e:
            print(f"Ошибка в decline_callback: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message("Произошла ошибка при обработке.", ephemeral=True)

    @discord.ui.button(label="Позвать на собес", style=discord.ButtonStyle.blurple, custom_id="interview_app")
    async def interview_callback(self, interaction: discord.Interaction, button: Button):
        try:
            voice_mention = f"<#{VOICE_CHANNEL_ID}>"
            await interaction.response.send_message(
                f"{self.applicant.mention}, Вас вызывают на собеседование! Зайдите в голосовой канал {voice_mention}",
                ephemeral=False
            )
        except Exception as e:
            print(f"Ошибка в interview_callback: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message("Произошла ошибка при обработке.", ephemeral=True)

class ApplicationModal(Modal, title="Анкета в семью"):
    def __init__(self):
        super().__init__()
        
        self.info_field = TextInput(label="Ник в игре | Статик | Имя и возраст", placeholder="Например: Player123 | PC | Иван, 20 лет", max_length=100)
        self.exp_field = TextInput(label="Опыт на RP серверах | Ежедневный онлайн", placeholder="Опыт: 1 год | Онлайн: 4 часа в день", style=discord.TextStyle.long, max_length=500)
        self.prev_families = TextInput(label="В каких семьях состояли до?", style=discord.TextStyle.long, max_length=1000, required=False)
        self.why_us = TextInput(label="Почему выбрали именно нас?", style=discord.TextStyle.long, max_length=1000)
        self.skills = TextInput(label="Ваши навыки стрельбы (Видео до 5 минут)", placeholder="Ссылка на видео", max_length=500, required=False)

        self.add_item(self.info_field)
        self.add_item(self.exp_field)
        self.add_item(self.prev_families)
        self.add_item(self.why_us)
        self.add_item(self.skills)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            category = interaction.guild.get_channel(CATEGORY_ID)
            
            if not category:
                print(f"ОШИБКА: Категория {CATEGORY_ID} не найдена!")
                await interaction.response.send_message("Ошибка: Категория для заявок не найдена. Обратитесь к администратору.", ephemeral=True)
                return

            if not isinstance(category, discord.CategoryChannel):
                print(f"ОШИБКА: Канал {CATEGORY_ID} не является категорией!")
                await interaction.response.send_message("Ошибка: Указанный ID не является категорией.", ephemeral=True)
                return

            channel_name = f"заявка-{interaction.user.name}"
            
            new_channel = await category.create_text_channel(
                name=channel_name,
                reason="Создание заявки в семью",
                topic=f"Заявка от {interaction.user.name}"
            )
            
            await new_channel.set_permissions(interaction.guild.default_role, view_channel=False)
            await new_channel.set_permissions(interaction.user, view_channel=True, send_messages=True)
            
            for role_id in TICKET_ADMIN_ROLES:
                role = interaction.guild.get_role(role_id)
                if role:
                    await new_channel.set_permissions(role, view_channel=True, send_messages=True)

            app_embed = discord.Embed(title=":file_folder: Анкета кандидата", color=discord.Color.blue())
            app_embed.set_author(name=interaction.user.name, icon_url=interaction.user.avatar.url)
            
            info_value = self.info_field.value.strip() if self.info_field.value and self.info_field.value.strip() else "❌ Не заполнено"
            app_embed.add_field(name="Ник в игре | Статик | Имя и возраст", value=info_value, inline=False)
            
            exp_value = self.exp_field.value.strip() if self.exp_field.value and self.exp_field.value.strip() else "❌ Не заполнено"
            app_embed.add_field(name="Опыт на RP серверах | Ежедневный онлайн", value=exp_value, inline=False)
            
            prev_value = self.prev_families.value.strip() if self.prev_families.value and self.prev_families.value.strip() else "💭 Не состоял(а) в других семьях"
            app_embed.add_field(name="В каких семьях состояли до?", value=prev_value, inline=False)
            
            why_value = self.why_us.value.strip() if self.why_us.value and self.why_us.value.strip() else "❌ Не заполнено"
            app_embed.add_field(name="Почему выбрали именно нас?", value=why_value, inline=False)
            
            skills_value = self.skills.value.strip() if self.skills.value and self.skills.value.strip() else "🎬 Не предоставлено (не обязательно)"
            app_embed.add_field(name="Ваши навыки стрельбы (Видео до 5 минут)", value=skills_value, inline=False)
            
            app_embed.set_footer(text=f"ID пользователя: {interaction.user.id}")

            notify_role = interaction.guild.get_role(NOTIFY_ROLE_ID)
            role_mention = notify_role.mention if notify_role else ""

            msg = await new_channel.send(f"{role_mention} Новая заявка от {interaction.user.mention}", embed=app_embed)
            
            view = TicketButtons(interaction.user, app_embed)
            await msg.edit(view=view)
            
            await interaction.response.send_message(f"Ваша заявка отправлена! Проверьте канал {new_channel.mention}", ephemeral=True)

        except Exception as e:
            error_trace = traceback.format_exc()
            print(f"=== ОШИБКА ПРИ СОЗДАНИИ КАНАЛА ===")
            print(f"Пользователь: {interaction.user.name} ({interaction.user.id})")
            print(f"Ошибка: {e}")
            print(f"Traceback:\n{error_trace}")
            print(f"=================================")
            
            try:
                await interaction.user.send(f"⚠️ Произошла ошибка при создании заявки:\n```\n{str(e)}\n```")
            except:
                pass
            
            if not interaction.response.is_done():
                await interaction.response.send_message("Произошла ошибка при создании канала. Администратор был уведомлен.", ephemeral=True)

class StartApplicationButton(View):
    # ✅ timeout=None чтобы кнопка работала постоянно
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="📩 Подать заявку в семью", style=discord.ButtonStyle.green, custom_id="start_app_btn")
    async def button_callback(self, interaction: discord.Interaction, button: Button):
        try:
            # ✅ Проверяем, не нажата ли кнопка уже
            await interaction.response.send_modal(ApplicationModal())
        except discord.errors.InteractionResponded:
            # Если уже ответили (редкий случай), игнорируем
            pass
        except Exception as e:
            print(f"Ошибка в button_callback: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message("Произошла ошибка при открытии формы. Попробуйте ещё раз.", ephemeral=True)

# --- КОМАНДЫ БОТА ---

@bot.command(name="заявка")
async def send_application_embed(ctx):
    try:
        await ctx.message.delete()
    except:
        pass
    
    if ctx.author.id == OWNER_ID:
        pass
    else:
        user_roles = [role.id for role in ctx.author.roles]
        if not any(role_id in user_roles for role_id in COMMAND_ALLOWED_ROLES):
            await ctx.send("У вас нет доступа к этой команде.", ephemeral=True)
            return

    embed = discord.Embed(
        title="🤝 Путь в семью начинается здесь!",
        description="После заполнения анкеты Вам придет оповещение в ЛС от бота с результатом.",
        color=discord.Color.gold()
    )
    
    embed.add_field(
        name="⏱️ Срок рассмотрения",
        value="Заявки обрабатываются от 2 до 24 часов — всё зависит от того, насколько загружены наши рекрутеры на данный момент.",
        inline=False
    )
    
    embed.set_image(url="https://i.imgur.com/bRqv7WM.jpeg")
    embed.set_thumbnail(url="https://i.imgur.com/kJy80lj.png")
    
    view = StartApplicationButton()
    await ctx.send(embed=embed, view=view)

@bot.command(name="rename")
async def rename_user_prefix(ctx, member: discord.Member, *, new_nickname: str):
    try:
        await ctx.message.delete()
    except:
        pass
    
    await rename_user_logic(ctx, member, new_nickname, is_slash=False)

@bot.tree.command(name="rename", description="Изменить никнейм пользователя на сервере")
@app_commands.describe(member="Пользователь, которому изменить никнейм", new_nickname="Новый никнейм (макс. 32 символа)")
async def rename_user_slash(interaction: discord.Interaction, member: discord.Member, new_nickname: str):
    await rename_user_logic(interaction, member, new_nickname, is_slash=True)

async def rename_user_logic(ctx_or_interaction, member: discord.Member, new_nickname: str, is_slash: bool = False):
    if is_slash:
        author = ctx_or_interaction.user
        response_method = ctx_or_interaction.response.send_message
    else:
        author = ctx_or_interaction.author
        response_method = ctx_or_interaction.send
    
    if author.id == OWNER_ID:
        pass
    else:
        user_roles = [role.id for role in author.roles]
        if not any(role_id in user_roles for role_id in RENAME_ALLOWED_ROLES):
            await response_method("❌ У вас нет прав использовать эту команду.", ephemeral=True)
            return
    
    if member == ctx_or_interaction.guild.owner:
        await response_method("❌ Нельзя изменить никнейм владельца сервера.", ephemeral=True)
        return
    
    if member == ctx_or_interaction.guild.me:
        await response_method("❌ Нельзя изменить никнейм самого бота этой командой.", ephemeral=True)
        return
    
    if len(new_nickname) > 32:
        await response_method("❌ Никнейм не может быть длиннее 32 символов.", ephemeral=True)
        return
    
    try:
        await member.edit(nick=new_nickname)
        
        embed = discord.Embed(
            title="✅ Никнейм изменён",
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="👤 Пользователь", value=member.mention, inline=True)
        embed.add_field(name="🔨 Изменил", value=author.mention, inline=True)
        embed.add_field(name="📝 Новый никнейм", value=new_nickname, inline=False)
        embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
        
        await response_method(embed=embed)
        
    except discord.Forbidden:
        await response_method("❌ У бота нет прав на изменение никнейма этого пользователя. Убедитесь, что роль бота находится выше роли пользователя.", ephemeral=True)
    except Exception as e:
        print(f"Ошибка при изменении никнейма: {e}")
        await response_method(f"❌ Произошла ошибка при изменении никнейма: `{str(e)}`", ephemeral=True)

@bot.event
async def on_ready():
    print(f'Бот запущен как {bot.user}')
    print(f'Категория заявок: {CATEGORY_ID}')
    print(f'Канал логов: {LOG_CHANNEL_ID}')
    print(f'Роль для уведомлений: {NOTIFY_ROLE_ID}')
    print(f'Владелец бота (полный доступ): {OWNER_ID}')
    print(f'Роль для выдачи 1: {ROLE_ADD_1}')
    print(f'Роль для выдачи 2: {ROLE_ADD_2}')
    print(f'Роль для удаления: {ROLE_REMOVE}')
    
    try:
        synced = await bot.tree.sync()
        print(f'Синхронизировано {len(synced)} слэш-команд')
    except Exception as e:
        print(f'Ошибка синхронизации слэш-команд: {e}')

# Запуск бота
bot.run(TOKEN)
