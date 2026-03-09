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

# 📁 Категория для личных веток
PRIVATE_CHANNEL_CATEGORY_ID = 1449567768524623972

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

# 🛠️ Роли, которые могут использовать команду !rename и !ветка
ADMIN_ROLES = [
    1449567765810778202,
    1449567765810778205,
    1449567765810778210,
    1449567765810778211
]

# 🎭 Роли для управления при принятии заявки
ROLE_ADD_1 = 1449567765798191154
ROLE_ADD_2 = 1449575866630934640
ROLE_REMOVE = 1449575999850418308

# 🔒 Роли, которые могут видеть личные ветки
PRIVATE_CHANNEL_VISIBLE_ROLES = [
    1449567765810778211,
    1449567765810778210,
    1449567765810778205
]

# 🎉 Роли для управления ивентами
EVENT_ADMIN_ROLES = [
    1449567765810778211,
    1449567765810778210,
    1449567765810778205
]

# --- ХРАНИЛИЩЕ ДАННЫХ ИВЕНТОВ ---
events_data = {}

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

def check_event_admin(user: discord.Member) -> bool:
    if user.id == OWNER_ID:
        return True
    user_roles = [role.id for role in user.roles]
    return any(role_id in user_roles for role_id in EVENT_ADMIN_ROLES)

# --- КЛАССЫ ИНТЕРФЕЙСА (UI) ---

class EventCreationModal(Modal, title="Создание ивента"):
    def __init__(self, channel: discord.TextChannel):
        super().__init__()
        self.channel = channel
        
        self.event_type = TextInput(
            label="Тип ивента",
            placeholder="Мероприятие, проверка активности, захват территории, война или своё",
            style=discord.TextStyle.short,
            max_length=100
        )
        
        self.event_date = TextInput(
            label="Дата проведения",
            placeholder="Например: 25.12.2024",
            style=discord.TextStyle.short,
            max_length=50
        )
        
        self.event_time = TextInput(
            label="Время проведения",
            placeholder="Например: 20:00 МСК",
            style=discord.TextStyle.short,
            max_length=50
        )
        
        self.event_location = TextInput(
            label="Место проведения",
            placeholder="Например: Сервер #1, координаты X:100 Y:200",
            style=discord.TextStyle.long,
            max_length=500
        )
        
        self.add_item(self.event_type)
        self.add_item(self.event_date)
        self.add_item(self.event_time)
        self.add_item(self.event_location)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            embed = discord.Embed(
                title=f"{self.event_type.value}",
                description=f"📅 **Дата:** {self.event_date.value}\n"
                           f"⏰ **Время:** {self.event_time.value}\n"
                           f"📍 **Место:** {self.event_location.value}\n\n"
                           f"Организатор: {interaction.user.mention}",
                color=discord.Color.gold(),
                timestamp=datetime.utcnow()
            )
            
            everyone_mention = "||@everyone||"
            
            embed.add_field(name="✅ Будет (0)", value="*Пока нет записавшихся*", inline=True)
            embed.add_field(name="❌ Не будет (0)", value="*Пока нет записавшихся*", inline=True)
            embed.add_field(name="⚠️ Убрал галочку (0)", value="*Пока нет записавшихся*", inline=True)
            
            embed.set_footer(text=f"ID ивента: {interaction.id}")
            
            view = EventView()
            
            message = await self.channel.send(content=everyone_mention, embed=embed, view=view)
            
            await message.add_reaction('✅')
            await message.add_reaction('❌')
            
            events_data[message.id] = {
                'will_attend': set(),
                'wont_attend': set(),
                'removed': set(),
                'message': message,
                'channel': self.channel
            }
            
            await interaction.response.send_message("✅ Ивент успешно создан!", ephemeral=True)
            
        except Exception as e:
            print(f"Ошибка при создании ивента: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ Произошла ошибка: `{str(e)}`", ephemeral=True)


class EventView(View):
    def __init__(self):
        super().__init__(timeout=None)
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not check_event_admin(interaction.user):
            await interaction.response.send_message("❌ У вас нет прав управлять этим ивентом.", ephemeral=True)
            return False
        return True
    
    @discord.ui.button(label="📢 Созвать всех", style=discord.ButtonStyle.red, custom_id="event_summon")
    async def summon_callback(self, interaction: discord.Interaction, button: Button):
        try:
            event_data = events_data.get(interaction.message.id)
            if not event_data:
                await interaction.response.send_message("❌ Данные ивента не найдены.", ephemeral=True)
                return
            
            will_attend = event_data['will_attend']
            
            if not will_attend:
                await interaction.response.send_message("⚠️ Нет участников в списке 'Будет'.", ephemeral=True)
                return
            
            dm_sent = 0
            dm_failed = 0
            
            for user_id in will_attend:
                try:
                    user = await interaction.guild.fetch_member(user_id)
                    await user.send("🔔 **Просыпаемся! Заходим в ГС и ИГРУ!**")
                    dm_sent += 1
                except:
                    dm_failed += 1
            
            mentions = []
            for user_id in will_attend:
                mentions.append(f"<@{user_id}>")
            
            mention_text = " ".join(mentions)
            
            await interaction.response.send_message(
                f"🔔 **Просыпаемся! Заходим в ГС и ИГРУ!**\n\n{mention_text}",
                ephemeral=False
            )
            
            print(f"Ивент: Отправлено {dm_sent} ЛС, не удалось {dm_failed}")
            
        except Exception as e:
            print(f"Ошибка в summon_callback: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ Произошла ошибка: `{str(e)}`", ephemeral=True)
    
    @discord.ui.button(label="🏁 Завершить", style=discord.ButtonStyle.gray, custom_id="event_end")
    async def end_callback(self, interaction: discord.Interaction, button: Button):
        try:
            await interaction.message.reply("🏁 **Событие завершено**")
            
            if interaction.message.id in events_data:
                events_data[interaction.message.id]['will_attend'].clear()
                events_data[interaction.message.id]['wont_attend'].clear()
                events_data[interaction.message.id]['removed'].clear()
            
            embed = interaction.message.embeds[0]
            
            for i, field in enumerate(embed.fields):
                if "Будет" in field.name:
                    embed.set_field_at(i, name="✅ Будет (0)", value="*Ивент завершён*", inline=True)
                elif "Не будет" in field.name:
                    embed.set_field_at(i, name="❌ Не будет (0)", value="*Ивент завершён*", inline=True)
                elif "Убрал галочку" in field.name:
                    embed.set_field_at(i, name="⚠️ Убрал галочку (0)", value="*Ивент завершён*", inline=True)
            
            # ✅ УДАЛЯЕМ ВСЕ РЕАКЦИИ (ГАЛОЧКУ И КРЕСТИК)
            try:
                await interaction.message.clear_reactions()
                print(f"Реакции удалены с ивента {interaction.message.id}")
            except Exception as react_error:
                print(f"Не удалось удалить реакции: {react_error}")
            
            await interaction.message.edit(embed=embed)
            await interaction.message.edit(view=None)
            
            if interaction.message.id in events_data:
                del events_data[interaction.message.id]
            
            await interaction.response.send_message("✅ Ивент завершён!", ephemeral=True)
            
        except Exception as e:
            print(f"Ошибка в end_callback: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ Произошла ошибка: `{str(e)}`", ephemeral=True)


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

    @discord.ui.button(label="Закрыть заявку", style=discord.ButtonStyle.gray, custom_id="close_ticket")
    async def close_callback(self, interaction: discord.Interaction, button: Button):
        try:
            log_channel = interaction.guild.get_channel(LOG_CHANNEL_ID)
            
            log_embed = discord.Embed(
                title="🚫 Заявка ЗАКРЫТА",
                color=discord.Color.gray(),
                timestamp=discord.utils.utcnow()
            )
            
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
            
            await interaction.response.send_message("Заявка закрыта! Канал будет удален через 5 секунд.", ephemeral=True)
            await asyncio.sleep(5)
            await interaction.channel.delete()
            
        except Exception as e:
            print(f"Ошибка в close_callback: {e}")
            print(f"Traceback: {traceback.format_exc()}")
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
            category = interaction.guild.get_channel(PRIVATE_CHANNEL_CATEGORY_ID)
            
            if not category:
                await interaction.response.send_message("❌ Категория для личных веток не найдена.", ephemeral=True)
                return
            
            if not isinstance(category, discord.CategoryChannel):
                await interaction.response.send_message("❌ Указанный ID не является категорией.", ephemeral=True)
                return
            
            server_nickname = interaction.user.display_name
            sanitized_name = sanitize_channel_name(server_nickname)
            channel_name = f"ветка-{sanitized_name}"
            
            new_channel = await category.create_text_channel(
                name=channel_name,
                reason="Создание личной ветки",
                topic=f"Личная ветка от {server_nickname}"
            )
            
            await new_channel.set_permissions(interaction.guild.default_role, view_channel=False, send_messages=False)
            await new_channel.set_permissions(interaction.user, view_channel=True, send_messages=True)
            
            for role_id in PRIVATE_CHANNEL_VISIBLE_ROLES:
                role = interaction.guild.get_role(role_id)
                if role:
                    await new_channel.set_permissions(role, view_channel=True, send_messages=True)
            
            embed = discord.Embed(
                title="🔒 Личная ветка создана",
                description=f"Добро пожаловать в вашу личную ветку, {interaction.user.mention}!\n\nЭтот канал виден только вам и администрации.",
                color=discord.Color.blurple()
            )
            embed.add_field(name="👤 Владелец", value=interaction.user.mention, inline=True)
            embed.add_field(name="📁 Категория", value=category.mention, inline=True)
            embed.add_field(name="🏷️ Серверный ник", value=server_nickname, inline=True)
            embed.set_footer(text=f"ID канала: {new_channel.id}")
            
            await new_channel.send(embed=embed)
            
            await interaction.response.send_message(
                f"✅ Ваша личная ветка создана: {new_channel.mention}",
                ephemeral=True
            )
            
        except Exception as e:
            print(f"Ошибка при создании личной ветки: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ Произошла ошибка при создании ветки: `{str(e)}`", ephemeral=True)


class ApplicationModal(Modal, title="Анкета в семью"):
    def __init__(self):
        super().__init__()
        
        self.info_field = TextInput(
            label="Игровой ник | Статик ID",
            placeholder="Например: Player123 | 12345",
            max_length=100
        )
        
        self.exp_field = TextInput(
            label="Опыт на RP серверах | Ежедневный онлайн",
            placeholder="Например: 1 год | 4 часа в день",
            style=discord.TextStyle.long,
            max_length=500
        )
        
        self.prev_families = TextInput(
            label="В каких семьях состояли до?",
            placeholder="(По какой причине покинули?)",
            style=discord.TextStyle.long,
            max_length=1000,
            required=False
        )
        
        self.why_us = TextInput(
            label="Почему выбрали именно нас?",
            placeholder="(Какую пользу сможете принести нашей семье?)",
            style=discord.TextStyle.long,
            max_length=1000
        )
        
        self.skills = TextInput(
            label="Ваши навыки стрельбы (Видео до 5 минут)",
            placeholder="(Видео откат с любого МП, файта, арены)",
            max_length=500,
            required=False
        )

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
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="📩 Подать заявку в семью", style=discord.ButtonStyle.green, custom_id="start_app_btn")
    async def button_callback(self, interaction: discord.Interaction, button: Button):
        try:
            await interaction.response.send_modal(ApplicationModal())
        except discord.errors.InteractionResponded:
            pass
        except Exception as e:
            print(f"Ошибка в button_callback: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message("Произошла ошибка при открытии формы. Попробуйте ещё раз.", ephemeral=True)

# --- КОМАНДЫ БОТА ---

@bot.tree.command(name="createevent", description="Создать ивент")
@app_commands.describe(channel="Канал для публикации ивента")
async def create_event(interaction: discord.Interaction, channel: discord.TextChannel):
    if not check_event_admin(interaction.user):
        await interaction.response.send_message("❌ У вас нет прав создавать ивенты.", ephemeral=True)
        return
    
    await interaction.response.send_modal(EventCreationModal(channel))

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
    
    embed = discord.Embed(
        title="🔒 Личная ветка",
        description="Нажмите на кнопку ниже, чтобы создать свою личную ветку.\n\nВ этой ветке сможете писать только вы и администрация сервера.",
        color=discord.Color.blurple()
    )
    embed.add_field(name="📁 Категория", value=f"<#{PRIVATE_CHANNEL_CATEGORY_ID}>", inline=True)
    embed.add_field(name="👥 Доступ", value="Только вы и администрация", inline=True)
    embed.set_footer(text="Личные ветки создаются автоматически")
    
    view = PrivateChannelButtons()
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
        if not any(role_id in user_roles for role_id in ADMIN_ROLES):
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

# --- ОБРАБОТКА РЕАКЦИЙ НА ИВЕНТЫ ---

@bot.event
async def on_raw_reaction_add(payload):
    if payload.message_id not in events_data:
        return
    
    if str(payload.emoji) not in ['✅', '❌']:
        return
    
    event_data = events_data[payload.message_id]
    user_id = payload.user_id
    
    if user_id == bot.user.id:
        return
    
    guild = bot.get_guild(payload.guild_id)
    if not guild:
        return
    
    will_attend = event_data['will_attend']
    wont_attend = event_data['wont_attend']
    removed = event_data['removed']
    
    if str(payload.emoji) == '✅':
        will_attend.add(user_id)
        wont_attend.discard(user_id)
        removed.discard(user_id)
    elif str(payload.emoji) == '❌':
        wont_attend.add(user_id)
        will_attend.discard(user_id)
        removed.discard(user_id)
    
    await update_event_embed(event_data)

@bot.event
async def on_raw_reaction_remove(payload):
    if payload.message_id not in events_data:
        return
    
    if str(payload.emoji) != '✅':
        return
    
    event_data = events_data[payload.message_id]
    user_id = payload.user_id
    
    if user_id == bot.user.id:
        return
    
    will_attend = event_data['will_attend']
    wont_attend = event_data['wont_attend']
    removed = event_data['removed']
    
    if user_id in will_attend:
        will_attend.discard(user_id)
        removed.add(user_id)
    
    await update_event_embed(event_data)

async def update_event_embed(event_data):
    message = event_data['message']
    will_attend = event_data['will_attend']
    wont_attend = event_data['wont_attend']
    removed = event_data['removed']
    
    embed = message.embeds[0]
    
    will_list = []
    wont_list = []
    removed_list = []
    
    for user_id in will_attend:
        will_list.append(f"<@{user_id}>")
    
    for user_id in wont_attend:
        wont_list.append(f"<@{user_id}>")
    
    for user_id in removed:
        removed_list.append(f"<@{user_id}>")
    
    for i, field in enumerate(embed.fields):
        if "Будет" in field.name:
            value = "\n".join(will_list) if will_list else "*Пока нет записавшихся*"
            embed.set_field_at(i, name=f"✅ Будет ({len(will_list)})", value=value, inline=True)
        elif "Не будет" in field.name:
            value = "\n".join(wont_list) if wont_list else "*Пока нет записавшихся*"
            embed.set_field_at(i, name=f"❌ Не будет ({len(wont_list)})", value=value, inline=True)
        elif "Убрал галочку" in field.name:
            value = "\n".join(removed_list) if removed_list else "*Пока нет записавшихся*"
            embed.set_field_at(i, name=f"⚠️ Убрал галочку ({len(removed_list)})", value=value, inline=True)
    
    await message.edit(embed=embed)

@bot.event
async def on_ready():
    print(f'Бот запущен как {bot.user}')
    print(f'Категория заявок: {CATEGORY_ID}')
    print(f'Категория личных веток: {PRIVATE_CHANNEL_CATEGORY_ID}')
    print(f'Канал логов: {LOG_CHANNEL_ID}')
    print(f'Роль для уведомлений: {NOTIFY_ROLE_ID}')
    print(f'Владелец бота (полный доступ): {OWNER_ID}')
    print(f'Роль для выдачи 1: {ROLE_ADD_1}')
    print(f'Роль для выдачи 2: {ROLE_ADD_2}')
    print(f'Роль для удаления: {ROLE_REMOVE}')
    
    bot.add_view(StartApplicationButton())
    bot.add_view(PrivateChannelButtons())
    bot.add_view(EventView())
    print('✅ Постоянные кнопки зарегистрированы')
    
    try:
        synced = await bot.tree.sync()
        print(f'Синхронизировано {len(synced)} слэш-команд')
    except Exception as e:
        print(f'Ошибка синхронизации слэш-команд: {e}')

# Запуск бота
bot.run(TOKEN)
