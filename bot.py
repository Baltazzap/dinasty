import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Button, View, Modal, TextInput
import os
import traceback
import asyncio
import re
from datetime import datetime

# Получение токена из переменной окружения DISCORD_TOKEN
TOKEN = os.getenv('DISCORD_TOKEN')

if not TOKEN:
    print("Ошибка: Токен не найден. Проверьте переменную окружения DISCORD_TOKEN")
    exit()

# --- КОНФИГУРАЦИЯ ID ---
CATEGORY_ID = 1451275518740791326
LOG_CHANNEL_ID = 1449573243735511153
VOICE_CHANNEL_ID = 1449567766666416148
PRIVATE_CHANNEL_CATEGORY_ID = 1449567768524623972
NOTIFY_ROLE_ID = 1449567765810778202
OWNER_ID = 314805583788244993
COMMAND_ALLOWED_ROLES = [1449567765844459572]
TICKET_ADMIN_ROLES = [1449567765810778202, 1449567765810778205, 1449567765810778210, 1449567765810778211]
ADMIN_ROLES = [1449567765810778202, 1449567765810778205, 1449567765810778210, 1449567765810778211]
ROLE_ADD_1 = 1449567765798191154
ROLE_ADD_2 = 1449575866630934640
ROLE_REMOVE = 1449575999850418308
PRIVATE_CHANNEL_VISIBLE_ROLES = [1449567765810778211, 1449567765810778210, 1449567765810778205]
MENU_ADMIN_ROLES = [1449567765810778211, 1449567765810778210, 1449567765810778205]

# --- ХРАНИЛИЩЕ ДАННЫХ ---
menu_data = {}
plus_messages = {}
user_channels = {}

# --- НАСТРОЙКИ БОТА ---
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.reactions = True

bot = commands.Bot(command_prefix='!', intents=intents)

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

def sanitize_channel_name(name: str) -> str:
    name = name.lower()
    name = name.replace(' ', '-').replace('_', '-')
    name = re.sub(r'[^a-zа-яё0-9-]', '', name)
    name = re.sub(r'-+', '-', name)
    name = name.strip('-')
    return name[:50] if name else 'ветка'

def check_menu_admin(user: discord.Member) -> bool:
    if user.id == OWNER_ID:
        return True
    user_roles = [role.id for role in user.roles]
    return any(role_id in user_roles for role_id in MENU_ADMIN_ROLES)

# --- КЛАССЫ ИНТЕРФЕЙСА (UI) ---

class DeclineReasonModal(Modal, title="Причина отклонения"):
    def __init__(self, applicant: discord.Member, application_embed: discord.Embed, ticket_channel: discord.TextChannel):
        super().__init__()
        self.applicant = applicant
        self.application_embed = application_embed
        self.ticket_channel = ticket_channel
        
        self.reason_input = TextInput(
            label="Укажите причину отклонения",
            placeholder="Например: Не подходит по возрасту / Мало опыта",
            style=discord.TextStyle.long,
            max_length=500,
            required=True
        )
        self.add_item(self.reason_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            reason = self.reason_input.value
            
            log_channel = interaction.guild.get_channel(LOG_CHANNEL_ID)
            if log_channel:
                log_embed = discord.Embed(title="❌ Заявка ОТКЛОНЕНА", color=discord.Color.red(), timestamp=discord.utils.utcnow())
                log_embed.add_field(name="👤 Кандидат", value=self.applicant.mention, inline=True)
                log_embed.add_field(name="🔨 Обработал", value=interaction.user.mention, inline=True)
                log_embed.add_field(name="📝 Причина отказа", value=reason, inline=False)
                log_embed.add_field(name="⠀", value="━━━━━━━━━━━━━━━━━━━━", inline=False)
                
                if self.application_embed and self.application_embed.fields:
                    for field in self.application_embed.fields:
                        log_embed.add_field(name=field.name, value=field.value[:1024], inline=field.inline)
                
                log_embed.set_footer(text=f"ID пользователя: {self.applicant.id}")
                if self.application_embed and self.application_embed.author:
                    log_embed.set_author(name=self.application_embed.author.name, icon_url=self.application_embed.author.icon_url)
                
                await log_channel.send(embed=log_embed)
            
            try:
                await self.applicant.send(f"❌ Ваша заявка в семью была отклонена.\n📝 **Причина:** {reason}")
            except:
                pass
            
            await interaction.response.send_message("Заявка отклонена! Канал будет удален через 5 секунд.", ephemeral=True)
            await asyncio.sleep(5)
            await self.ticket_channel.delete()
            
        except Exception as e:
            print(f"Ошибка в DeclineReasonModal.on_submit: {e}")
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(f"❌ Произошла ошибка.", ephemeral=True)
                else:
                    await interaction.followup.send(f"❌ Произошла ошибка.", ephemeral=True)
            except:
                pass


class EditMenuModal(Modal, title="Редактировать меню"):
    def __init__(self, menu_id: int, current_title: str):
        super().__init__()
        self.menu_id = menu_id
        self.current_title = current_title
        self.menu_title = TextInput(label="Название меню", default=current_title, style=discord.TextStyle.short, max_length=100)
        self.add_item(self.menu_title)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            data = menu_data.get(self.menu_id)
            if not data:
                await interaction.response.send_message("❌ Меню не найдено.", ephemeral=True)
                return
            embed = data['message'].embeds[0]
            embed.title = self.menu_title.value
            await data['message'].edit(embed=embed)
            await interaction.response.send_message(f"✅ Название изменено на: `{self.menu_title.value}`", ephemeral=True)
        except Exception as e:
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ Ошибка: `{str(e)}`", ephemeral=True)


class MenuView(View):
    def __init__(self):
        super().__init__(timeout=None)
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        try:
            if not check_menu_admin(interaction.user):
                await interaction.response.send_message("❌ У вас нет прав управлять этим меню.", ephemeral=True)
                return False
            return True
        except Exception as e:
            print(f"Ошибка в interaction_check: {e}")
            return False
    
    @discord.ui.button(label="🏁 Завершить", style=discord.ButtonStyle.gray, custom_id="menu_end")
    async def end_callback(self, interaction: discord.Interaction, button: Button):
        try:
            data = menu_data.get(interaction.message.id)
            if not data:
                menu_data[interaction.message.id] = {
                    'will_attend': {},
                    'removed': set(),
                    'message': interaction.message,
                    'thread': None,
                    'is_active': False
                }
                data = menu_data[interaction.message.id]
            
            if data.get('thread'):
                try:
                    await data['thread'].delete()
                except:
                    pass
                data['thread'] = None
            
            data['will_attend'].clear()
            data['removed'].clear()
            data['is_active'] = False
            
            embed = interaction.message.embeds[0]
            for i, field in enumerate(embed.fields):
                if "ОСНОВА" in field.name:
                    embed.set_field_at(i, name="✅ОСНОВА (0)", value="*Сбор завершен*", inline=True)
                elif "УБРАЛИ ПЛЮС" in field.name:
                    embed.set_field_at(i, name="❌УБРАЛИ ПЛЮС (0)", value="*Сбор завершен*", inline=True)
                elif "Статус" in field.name:
                    embed.set_field_at(i, name="**Статус**", value="🔴Сбор закрыт (ветка удалена)", inline=False)
            
            await interaction.message.edit(embed=embed, view=MenuView())
            
            if not interaction.response.is_done():
                await interaction.response.send_message("✅ Сбор завершен! Ветка удалена.", ephemeral=True)
            
        except Exception as e:
            print(f"Ошибка в end_callback: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ Ошибка: `{str(e)}`", ephemeral=True)
    
    @discord.ui.button(label="▶️ Возобновить", style=discord.ButtonStyle.green, custom_id="menu_resume")
    async def resume_callback(self, interaction: discord.Interaction, button: Button):
        try:
            data = menu_data.get(interaction.message.id)
            if not data:
                menu_data[interaction.message.id] = {
                    'will_attend': {},
                    'removed': set(),
                    'message': interaction.message,
                    'thread': None,
                    'is_active': False
                }
                data = menu_data[interaction.message.id]
            
            data['is_active'] = True
            thread = await interaction.message.create_thread(name="Плюсы", reason="Возобновление сбора активности")
            data['thread'] = thread
            data['start_time'] = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
            
            embed = interaction.message.embeds[0]
            for i, field in enumerate(embed.fields):
                if "Начало" in field.name:
                    embed.set_field_at(i, name="**Начало**", value=data['start_time'], inline=False)
                elif "Статус" in field.name:
                    embed.set_field_at(i, name="**Статус**", value="🟢Сбор открыт (Пиши + в ветку)", inline=False)
            
            await interaction.message.edit(embed=embed, view=MenuView())
            await thread.send(f"📝 **Пиши `+` в ветку, админ поставит ✅ для записи**\n\nВетка возобновлена: {data['start_time']}")
            
            if not interaction.response.is_done():
                await interaction.response.send_message(f"✅ Сбор возобновлен! Ветка создана: {thread.mention}", ephemeral=True)
            
        except Exception as e:
            print(f"Ошибка в resume_callback: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ Ошибка: `{str(e)}`", ephemeral=True)
    
    @discord.ui.button(label="📢 Позвать всех", style=discord.ButtonStyle.red, custom_id="menu_summon")
    async def summon_callback(self, interaction: discord.Interaction, button: Button):
        try:
            data = menu_data.get(interaction.message.id)
            if not data:
                await interaction.response.send_message("❌ Данные меню не найдены. Возобновите сбор.", ephemeral=True)
                return
            thread = data.get('thread')
            if not thread:
                await interaction.response.send_message("❌ Ветка не найдена. Нажмите 'Возобновить'.", ephemeral=True)
                return
            await thread.send("||@everyone||\n\n🔔 **Заходим в ВОЙС и в ИГРУ!**")
            
            if not interaction.response.is_done():
                await interaction.response.send_message("✅ Все позваны в ветку!", ephemeral=True)
            
        except Exception as e:
            print(f"Ошибка в summon_callback: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ Ошибка: `{str(e)}`", ephemeral=True)
    
    @discord.ui.button(label="✏️ Редактировать", style=discord.ButtonStyle.blurple, custom_id="menu_edit")
    async def edit_callback(self, interaction: discord.Interaction, button: Button):
        try:
            data = menu_data.get(interaction.message.id)
            if not data:
                await interaction.response.send_message("❌ Данные меню не найдены.", ephemeral=True)
                return
            embed = interaction.message.embeds[0]
            
            if not interaction.response.is_done():
                await interaction.response.send_modal(EditMenuModal(interaction.message.id, embed.title))
            
        except Exception as e:
            print(f"Ошибка в edit_callback: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ Ошибка: `{str(e)}`", ephemeral=True)
    
    @discord.ui.button(label="🔔 Напомнить всем (ЛС)", style=discord.ButtonStyle.blurple, custom_id="menu_remind")
    async def remind_callback(self, interaction: discord.Interaction, button: Button):
        try:
            data = menu_data.get(interaction.message.id)
            if not data:
                await interaction.response.send_message("❌ Данные меню не найдены.", ephemeral=True)
                return
            will_attend = data['will_attend']
            if not will_attend:
                await interaction.response.send_message("⚠️ Нет участников в списке 'ОСНОВА'.", ephemeral=True)
                return
            dm_sent = 0
            dm_failed = 0
            for user_id in will_attend.keys():
                try:
                    user = await interaction.guild.fetch_member(user_id)
                    await user.send("🔔 **Ты записан в ОСНОВУ, Заходим в ВОЙС и в ИГРУ!**")
                    dm_sent += 1
                except:
                    dm_failed += 1
            
            if not interaction.response.is_done():
                await interaction.response.send_message(f"✅ Отправлено {dm_sent} ЛС, не удалось {dm_failed}", ephemeral=True)
            
        except Exception as e:
            print(f"Ошибка в remind_callback: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ Ошибка: `{str(e)}`", ephemeral=True)


class MenuCreationModal(Modal, title="Создание меню активности"):
    def __init__(self):
        super().__init__()
        self.menu_title = TextInput(label="Название меню", placeholder="Например: Меню Активности", style=discord.TextStyle.short, max_length=100, default="Меню Активности")
        self.add_item(self.menu_title)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            start_time = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
            embed = discord.Embed(title=f"{self.menu_title.value}", color=discord.Color.gold(), timestamp=datetime.utcnow())
            embed.add_field(name="**Начало**", value=start_time, inline=False)
            embed.add_field(name="**Инструкция**", value="Пиши `+` в ветку, админ поставит ✅ для записи", inline=False)
            embed.add_field(name="✅ОСНОВА (0)", value="*Пока нет записавшихся*", inline=True)
            embed.add_field(name="❌УБРАЛИ ПЛЮС (0)", value="*Пока нет записавшихся*", inline=True)
            embed.add_field(name="**Статус**", value="🟢Сбор открыт (Пиши + в ветку)", inline=False)
            embed.set_footer(text=f"ID меню: {interaction.id}")
            
            view = MenuView()
            message = await interaction.channel.send(embed=embed, view=view)
            thread = await message.create_thread(name="Плюсы", reason="Создание меню активности")
            await thread.send(f"📝 **Пиши `+` в ветку, админ поставит ✅ для записи**\n\nВетка создана: {start_time}")
            
            menu_data[message.id] = {
                'will_attend': {},
                'removed': set(),
                'message': message,
                'thread': thread,
                'start_time': start_time,
                'is_active': True
            }
            
            if not interaction.response.is_done():
                await interaction.response.send_message(f"✅ Меню активности создано!\n\nВетка: {thread.mention}", ephemeral=True)
            
        except Exception as e:
            print(f"Ошибка при создании меню: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ Ошибка: `{str(e)}`", ephemeral=True)


class TicketButtons(View):
    def __init__(self, applicant: discord.Member, application_embed: discord.Embed, ticket_channel: discord.TextChannel):
        super().__init__(timeout=None)
        self.applicant = applicant
        self.application_embed = application_embed
        self.ticket_channel = ticket_channel

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        try:
            if interaction.user.id == OWNER_ID:
                return True
            user_roles = [role.id for role in interaction.user.roles]
            if not any(role_id in user_roles for role_id in TICKET_ADMIN_ROLES):
                await interaction.response.send_message("У вас нет прав использовать эти кнопки.", ephemeral=True)
                return False
            return True
        except Exception as e:
            print(f"Ошибка в interaction_check: {e}")
            return False

    async def send_to_logs(self, interaction: discord.Interaction, status: str, color: discord.Color):
        try:
            log_channel = interaction.guild.get_channel(LOG_CHANNEL_ID)
            if not log_channel:
                return
            log_embed = discord.Embed(title=f"{status}", color=color, timestamp=discord.utils.utcnow())
            log_embed.add_field(name="👤 Кандидат", value=self.applicant.mention, inline=True)
            log_embed.add_field(name="🔨 Обработал", value=interaction.user.mention, inline=True)
            log_embed.add_field(name="⠀", value="━━━━━━━━━━━━━━━━━━━━", inline=False)
            if self.application_embed and self.application_embed.fields:
                for field in self.application_embed.fields:
                    log_embed.add_field(name=field.name, value=field.value, inline=field.inline)
            log_embed.set_footer(text=f"ID пользователя: {self.applicant.id}")
            if self.application_embed and self.application_embed.author:
                log_embed.set_author(name=self.application_embed.author.name, icon_url=self.application_embed.author.icon_url)
            await log_channel.send(embed=log_embed)
        except Exception as e:
            print(f"Ошибка в send_to_logs: {e}")

    def get_nickname_from_embed(self):
        if self.application_embed and self.application_embed.fields:
            first_field = self.application_embed.fields[0]
            value = first_field.value
            if value and value != "❌ Не заполнено":
                return value[:32]
        return None

    @discord.ui.button(label="Принять", style=discord.ButtonStyle.green, custom_id="accept_app")
    async def accept_callback(self, interaction: discord.Interaction, button: Button):
        try:
            nickname_changed = False
            new_nickname = self.get_nickname_from_embed()
            if new_nickname:
                try:
                    await self.applicant.edit(nick=new_nickname)
                    nickname_changed = True
                except Exception as nick_error:
                    print(f"Не удалось изменить никнейм: {nick_error}")
            
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
            
            msg = "Заявка принята! "
            if nickname_changed:
                msg += f"Никнейм изменён на `{new_nickname}`. "
            msg += "Роли выданы. Канал будет удален через 5 секунд."
            
            if not interaction.response.is_done():
                await interaction.response.send_message(msg, ephemeral=True)
            await asyncio.sleep(5)
            await interaction.channel.delete()
            
        except Exception as e:
            print(f"Ошибка в accept_callback: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message("Произошла ошибка при обработке.", ephemeral=True)

    @discord.ui.button(label="Отклонить", style=discord.ButtonStyle.red, custom_id="decline_app")
    async def decline_callback(self, interaction: discord.Interaction, button: Button):
        try:
            if not interaction.response.is_done():
                await interaction.response.send_modal(
                    DeclineReasonModal(self.applicant, self.application_embed, self.ticket_channel)
                )
        except Exception as e:
            print(f"Ошибка в decline_callback: {e}")
            print(f"Traceback: {traceback.format_exc()}")
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ Произошла ошибка: `{str(e)}`", ephemeral=True)

    @discord.ui.button(label="Позвать на собес", style=discord.ButtonStyle.blurple, custom_id="interview_app")
    async def interview_callback(self, interaction: discord.Interaction, button: Button):
        try:
            voice_mention = f"<#{VOICE_CHANNEL_ID}>"
            if not interaction.response.is_done():
                await interaction.response.send_message(f"{self.applicant.mention}, Вас вызывают на собеседование! Зайдите в голосовой канал {voice_mention}", ephemeral=False)
        except Exception as e:
            print(f"Ошибка в interview_callback: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message("Произошла ошибка при обработке.", ephemeral=True)

    @discord.ui.button(label="Закрыть заявку", style=discord.ButtonStyle.gray, custom_id="close_ticket")
    async def close_callback(self, interaction: discord.Interaction, button: Button):
        try:
            log_channel = interaction.guild.get_channel(LOG_CHANNEL_ID)
            log_embed = discord.Embed(title="🚫 Заявка ЗАКРЫТА", color=discord.Color.gray(), timestamp=discord.utils.utcnow())
            try:
                candidate_mention = self.applicant.mention
            except:
                candidate_mention = f"<@{self.applicant.id}>"
            log_embed.add_field(name="👤 Кандидат", value=candidate_mention, inline=True)
            log_embed.add_field(name="🔨 Закрыл", value=interaction.user.mention, inline=True)
            log_embed.add_field(name="📝 Причина", value="Без решения (закрыто администратором)", inline=False)
            log_embed.add_field(name="⠀", value="━━━━━━━━━━━━━━━━━━━━", inline=False)
            if self.application_embed and self.application_embed.fields:
                for field in self.application_embed.fields:
                    log_embed.add_field(name=field.name, value=field.value[:1024], inline=field.inline)
            log_embed.set_footer(text=f"ID пользователя: {self.applicant.id}")
            if log_channel:
                try:
                    await log_channel.send(embed=log_embed)
                except Exception as log_error:
                    print(f"Не удалось отправить в логи: {log_error}")
            
            if not interaction.response.is_done():
                await interaction.response.send_message("Заявка закрыта! Канал будет удален через 5 секунд.", ephemeral=True)
            await asyncio.sleep(5)
            await interaction.channel.delete()
            
        except Exception as e:
            print(f"Ошибка в close_callback: {e}")
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("Произошла ошибка, но канал будет удален.", ephemeral=True)
                else:
                    await interaction.followup.send("Произошла ошибка, но канал будет удален.", ephemeral=True)
                await asyncio.sleep(5)
                await interaction.channel.delete()
            except:
                pass


class PrivateChannelButtons(View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="🔒 Создать личную ветку", style=discord.ButtonStyle.blurple, custom_id="create_private_channel")
    async def create_channel_callback(self, interaction: discord.Interaction, button: Button):
        try:
            user_id = interaction.user.id
            if user_id in user_channels:
                channel_id = user_channels[user_id]
                channel = interaction.guild.get_channel(channel_id)
                if channel:
                    if not interaction.response.is_done():
                        await interaction.response.send_message(f"⚠️ **У вас уже есть личная ветка!**\n\n📁 Ваш канал: {channel.mention}", ephemeral=True)
                    return
                else:
                    del user_channels[user_id]
            
            category = interaction.guild.get_channel(PRIVATE_CHANNEL_CATEGORY_ID)
            if not category:
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ Категория для личных веток не найдена.", ephemeral=True)
                return
            if not isinstance(category, discord.CategoryChannel):
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ Указанный ID не является категорией.", ephemeral=True)
                return
            
            server_nickname = interaction.user.display_name
            sanitized_name = sanitize_channel_name(server_nickname)
            channel_name = f"ветка-{sanitized_name}"
            new_channel = await category.create_text_channel(name=channel_name, reason="Создание личной ветки", topic=f"Личная ветка от {server_nickname}")
            
            await new_channel.set_permissions(interaction.guild.default_role, view_channel=False, send_messages=False)
            await new_channel.set_permissions(interaction.user, view_channel=True, send_messages=True)
            for role_id in PRIVATE_CHANNEL_VISIBLE_ROLES:
                role = interaction.guild.get_role(role_id)
                if role:
                    await new_channel.set_permissions(role, view_channel=True, send_messages=True)
            
            user_channels[user_id] = new_channel.id
            
            embed = discord.Embed(title="🔒 Личная ветка создана", description=f"Добро пожаловать в вашу личную ветку, {interaction.user.mention}!", color=discord.Color.blurple())
            embed.add_field(name="👤 Владелец", value=interaction.user.mention, inline=True)
            embed.add_field(name="📁 Категория", value=category.mention, inline=True)
            embed.add_field(name="🏷️ Серверный ник", value=server_nickname, inline=True)
            embed.set_footer(text=f"ID канала: {new_channel.id}")
            
            view_with_close = PrivateChannelCloseButton()
            await new_channel.send(embed=embed, view=view_with_close)
            
            if not interaction.response.is_done():
                await interaction.response.send_message(f"✅ Ваша личная ветка создана: {new_channel.mention}", ephemeral=True)
            
        except Exception as e:
            print(f"Ошибка при создании личной ветки: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ Ошибка: `{str(e)}`", ephemeral=True)


class PrivateChannelCloseButton(View):
    def __init__(self):
        super().__init__(timeout=None)
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        try:
            if interaction.user.id == OWNER_ID:
                return True
            user_roles = [role.id for role in interaction.user.roles]
            if not any(role_id in user_roles for role_id in ADMIN_ROLES):
                await interaction.response.send_message("❌ У вас нет прав закрыть эту ветку.", ephemeral=True)
                return False
            return True
        except Exception as e:
            print(f"Ошибка в interaction_check: {e}")
            return False
    
    @discord.ui.button(label="🔒 Закрыть ветку", style=discord.ButtonStyle.red, custom_id="close_private_channel")
    async def close_callback(self, interaction: discord.Interaction, button: Button):
        try:
            channel = interaction.channel
            for user_id, chan_id in list(user_channels.items()):
                if chan_id == channel.id:
                    del user_channels[user_id]
                    break
            
            if not interaction.response.is_done():
                await interaction.response.send_message("🔒 Ветка закрывается через 5 секунд...", ephemeral=True)
            await asyncio.sleep(5)
            await channel.delete()
            
        except Exception as e:
            print(f"Ошибка при закрытии ветки: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ Ошибка: `{str(e)}`", ephemeral=True)


class ApplicationModal(Modal, title="Анкета в семью"):
    def __init__(self):
        super().__init__()
        self.info_field = TextInput(label="Игровой ник | Статик ID", placeholder="Например: Player123 | 12345", max_length=100)
        self.exp_field = TextInput(label="Опыт на RP серверах | Ежедневный онлайн", placeholder="Например: 1 год | 4 часа в день", style=discord.TextStyle.long, max_length=500)
        self.prev_families = TextInput(label="В каких семьях состояли до?", placeholder="(По какой причине покинули?)", style=discord.TextStyle.long, max_length=1000, required=False)
        self.why_us = TextInput(label="Почему выбрали именно нас?", placeholder="(Какую пользу сможете принести нашей семье?)", style=discord.TextStyle.long, max_length=1000)
        self.skills = TextInput(label="Ваши навыки стрельбы (Видео до 5 минут)", placeholder="(Видео откат с любого МП, файта, арены)", max_length=500, required=False)
        self.add_item(self.info_field)
        self.add_item(self.exp_field)
        self.add_item(self.prev_families)
        self.add_item(self.why_us)
        self.add_item(self.skills)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            # ✅ ПЕРВОЕ ДЕЙСТВИЕ - ОТКЛАДЫВАЕМ ОТВЕТ
            await interaction.response.defer(ephemeral=True)
            
            category = interaction.guild.get_channel(CATEGORY_ID)
            if not category:
                await interaction.followup.send("❌ Категория для заявок не найдена.", ephemeral=True)
                return
            if not isinstance(category, discord.CategoryChannel):
                await interaction.followup.send("❌ Указанный ID не является категорией.", ephemeral=True)
                return

            channel_name = f"заявка-{interaction.user.name}"
            new_channel = await category.create_text_channel(name=channel_name, reason="Создание заявки в семью", topic=f"Заявка от {interaction.user.name}")
            
            await new_channel.set_permissions(interaction.guild.default_role, view_channel=False)
            await new_channel.set_permissions(interaction.user, view_channel=True, send_messages=True)
            for role_id in TICKET_ADMIN_ROLES:
                role = interaction.guild.get_role(role_id)
                if role:
                    await new_channel.set_permissions(role, view_channel=True, send_messages=True)

            app_embed = discord.Embed(title=":file_folder: Анкета кандидата", color=discord.Color.blue())
            app_embed.set_author(name=interaction.user.name, icon_url=interaction.user.avatar.url)
            
            info_value = self.info_field.value.strip() if self.info_field.value and self.info_field.value.strip() else "❌ Не заполнено"
            app_embed.add_field(name="Игровой ник | Статик ID", value=info_value, inline=False)
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
            
            view = TicketButtons(interaction.user, app_embed, new_channel)
            await msg.edit(view=view)
            
            await interaction.followup.send(f"✅ Ваша заявка отправлена! Проверьте канал {new_channel.mention}", ephemeral=True)
            
        except Exception as e:
            error_trace = traceback.format_exc()
            print(f"=== ОШИБКА ПРИ СОЗДАНИИ ЗАЯВКИ ===")
            print(f"Пользователь: {interaction.user.name} ({interaction.user.id})")
            print(f"Ошибка: {e}")
            print(f"Traceback:\n{error_trace}")
            print(f"=================================")
            try:
                await interaction.followup.send("❌ Произошла ошибка при создании заявки. Администратор уведомлен.", ephemeral=True)
            except:
                pass


class StartApplicationButton(View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="📩 Подать заявку в семью", style=discord.ButtonStyle.green, custom_id="start_app_btn")
    async def button_callback(self, interaction: discord.Interaction, button: Button):
        try:
            if not interaction.response.is_done():
                await interaction.response.send_modal(ApplicationModal())
        except discord.errors.InteractionResponded:
            pass
        except Exception as e:
            print(f"Ошибка в button_callback: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message("Произошла ошибка при открытии формы.", ephemeral=True)


# --- КОМАНДЫ БОТА ---

@bot.tree.command(name="menu", description="Создать меню активности")
async def menu_command(interaction: discord.Interaction):
    try:
        if not check_menu_admin(interaction.user):
            await interaction.response.send_message("❌ У вас нет прав использовать эту команду.", ephemeral=True)
            return
        await interaction.response.send_modal(MenuCreationModal())
    except Exception as e:
        print(f"Ошибка в menu_command: {e}")
        if not interaction.response.is_done():
            await interaction.response.send_message(f"❌ Ошибка: `{str(e)}`", ephemeral=True)

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
    embed = discord.Embed(title="🤝 Путь в семью начинается здесь!", description="После заполнения анкеты Вам придет оповещение в ЛС от бота с результатом.", color=discord.Color.gold())
    embed.add_field(name="⏱️ Срок рассмотрения", value="Заявки обрабатываются от 2 до 24 часов.", inline=False)
    embed.set_image(url="https://i.imgur.com/bRqv7WM.jpeg")
    embed.set_thumbnail(url="https://i.imgur.com/kJy80lj.png")
    view = StartApplicationButton()
    await ctx.send(embed=embed, view=view)

@bot.command(name="ветка")
async def private_channel_command(ctx):
    try:
        await ctx.message.delete()
    except:
        pass
    if ctx.author.id == OWNER_ID:
        pass
    else:
        user_roles = [role.id for role in ctx.author.roles]
        if not any(role_id in user_roles for role_id in ADMIN_ROLES):
            await ctx.send("❌ У вас нет прав использовать эту команду.", ephemeral=True)
            return
    embed = discord.Embed(title="🔒 Личная ветка", description="Нажмите на кнопку ниже, чтобы создать свою личную ветку.", color=discord.Color.blurple())
    embed.add_field(name="📁 Категория", value=f"<#{PRIVATE_CHANNEL_CATEGORY_ID}>", inline=True)
    embed.add_field(name="👥 Доступ", value="Только вы и администрация", inline=True)
    view = PrivateChannelButtons()
    await ctx.send(embed=embed, view=view)

@bot.tree.command(name="ветка", description="Создать эмбед для создания личной ветки")
async def private_channel_slash(interaction: discord.Interaction):
    try:
        if interaction.user.id == OWNER_ID:
            pass
        else:
            user_roles = [role.id for role in interaction.user.roles]
            if not any(role_id in user_roles for role_id in ADMIN_ROLES):
                await interaction.response.send_message("❌ У вас нет прав использовать эту команду.", ephemeral=True)
                return
        embed = discord.Embed(title="🔒 Личная ветка", description="Нажмите на кнопку ниже, чтобы создать свою личную ветку.", color=discord.Color.blurple())
        embed.add_field(name="📁 Категория", value=f"<#{PRIVATE_CHANNEL_CATEGORY_ID}>", inline=True)
        embed.add_field(name="👥 Доступ", value="Только вы и администрация", inline=True)
        view = PrivateChannelButtons()
        await interaction.response.send_message(embed=embed, view=view)
    except Exception as e:
        print(f"Ошибка в private_channel_slash: {e}")
        if not interaction.response.is_done():
            await interaction.response.send_message(f"❌ Ошибка: `{str(e)}`", ephemeral=True)

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
    try:
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
            if not any(role_id in user_roles for role_id in ADMIN_ROLES):
                await response_method("❌ У вас нет прав использовать эту команду.", ephemeral=True)
                return
        if member == ctx_or_interaction.guild.owner:
            await response_method("❌ Нельзя изменить никнейм владельца сервера.", ephemeral=True)
            return
        if member == ctx_or_interaction.guild.me:
            await response_method("❌ Нельзя изменить никнейм самого бота.", ephemeral=True)
            return
        if len(new_nickname) > 32:
            await response_method("❌ Никнейм не может быть длиннее 32 символов.", ephemeral=True)
            return
        await member.edit(nick=new_nickname)
        embed = discord.Embed(title="✅ Никнейм изменён", color=discord.Color.green(), timestamp=discord.utils.utcnow())
        embed.add_field(name="👤 Пользователь", value=member.mention, inline=True)
        embed.add_field(name="🔨 Изменил", value=author.mention, inline=True)
        embed.add_field(name="📝 Новый никнейм", value=new_nickname, inline=False)
        await response_method(embed=embed)
    except discord.Forbidden:
        await response_method("❌ У бота нет прав на изменение никнейма.", ephemeral=True)
    except Exception as e:
        await response_method(f"❌ Ошибка: `{str(e)}`", ephemeral=True)


# --- ОБРАБОТКА РЕАКЦИЙ НА "+" В ВЕТКЕ МЕНЮ ---

@bot.event
async def on_raw_reaction_add(payload):
    try:
        if str(payload.emoji) != '✅':
            return
        guild = bot.get_guild(payload.guild_id)
        if not guild:
            return
        user = guild.get_member(payload.user_id)
        if not user:
            return
        if not check_menu_admin(user):
            return
        if payload.message_id not in plus_messages:
            return
        menu_id = plus_messages[payload.message_id]
        data = menu_data.get(menu_id)
        if not data:
            return
        channel = guild.get_channel(payload.channel_id)
        if not channel:
            return
        try:
            message = await channel.fetch_message(payload.message_id)
            plus_author_id = message.author.id
            data['will_attend'][plus_author_id] = payload.message_id
            try:
                await message.remove_reaction('✅', user)
            except:
                pass
            await update_menu_embed(data)
        except Exception as e:
            print(f"Ошибка при обработке реакции: {e}")
    except Exception as e:
        print(f"Ошибка в on_raw_reaction_add: {e}")

@bot.event
async def on_raw_reaction_remove(payload):
    try:
        if str(payload.emoji) != '✅':
            return
        guild = bot.get_guild(payload.guild_id)
        if not guild:
            return
        if payload.message_id not in plus_messages:
            return
        menu_id = plus_messages[payload.message_id]
        data = menu_data.get(menu_id)
        if not data:
            return
        channel = guild.get_channel(payload.channel_id)
        if not channel:
            return
        try:
            message = await channel.fetch_message(payload.message_id)
            plus_author_id = message.author.id
            if plus_author_id in data['will_attend']:
                del data['will_attend'][plus_author_id]
            await update_menu_embed(data)
        except:
            pass
    except Exception as e:
        print(f"Ошибка в on_raw_reaction_remove: {e}")

@bot.event
async def on_message(message):
    try:
        if message.content.strip().lower() in ['+', 'плюс']:
            for menu_id, data in menu_data.items():
                if data.get('thread') and message.channel.id == data['thread'].id:
                    if data['is_active']:
                        plus_messages[message.id] = menu_id
                        try:
                            await message.add_reaction('⏳')
                        except:
                            pass
                        break
    except Exception as e:
        print(f"Ошибка в on_message: {e}")
    await bot.process_commands(message)

@bot.event
async def on_message_delete(message):
    try:
        if message.id in plus_messages:
            menu_id = plus_messages[message.id]
            data = menu_data.get(menu_id)
            if data:
                user_id = message.author.id
                if user_id in data['will_attend']:
                    del data['will_attend'][user_id]
                data['removed'].add(user_id)
                del plus_messages[message.id]
                await update_menu_embed(data)
    except Exception as e:
        print(f"Ошибка в on_message_delete: {e}")

async def update_menu_embed(data):
    try:
        message = data['message']
        will_attend = data['will_attend']
        removed = data['removed']
        embed = message.embeds[0]
        will_list = [f"<@{uid}>" for uid in will_attend.keys()]
        removed_list = [f"<@{uid}>" for uid in removed]
        for i, field in enumerate(embed.fields):
            if "ОСНОВА" in field.name:
                embed.set_field_at(i, name=f"✅ОСНОВА ({len(will_list)})", value="\n".join(will_list) or "*Пока нет*", inline=True)
            elif "УБРАЛИ ПЛЮС" in field.name:
                embed.set_field_at(i, name=f"❌УБРАЛИ ПЛЮС ({len(removed_list)})", value="\n".join(removed_list) or "*Пока нет*", inline=True)
        await message.edit(embed=embed)
    except Exception as e:
        print(f"Ошибка в update_menu_embed: {e}")

@bot.event
async def on_ready():
    try:
        await bot.change_presence(status=discord.Status.dnd)
        print(f'Бот запущен как {bot.user}')
        print(f'Статус: Не беспокоить (🔴)')
        print(f'Категория заявок: {CATEGORY_ID}')
        print(f'Категория личных веток: {PRIVATE_CHANNEL_CATEGORY_ID}')
        print(f'Канал логов: {LOG_CHANNEL_ID}')
        print(f'Владелец бота: {OWNER_ID}')
        print(f'Хранилище веток: {len(user_channels)} записей')
        
        bot.add_view(StartApplicationButton())
        bot.add_view(PrivateChannelButtons())
        bot.add_view(PrivateChannelCloseButton())
        bot.add_view(MenuView())
        print('✅ Постоянные кнопки зарегистрированы')
        
        synced = await bot.tree.sync()
        print(f'Синхронизировано {len(synced)} слэш-команд')
    except Exception as e:
        print(f'Ошибка в on_ready: {e}')

bot.run(TOKEN)
