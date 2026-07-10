from datetime import datetime, timedelta
import re
import sqlite3

import discord
from discord.ext import commands
from discord.commands import SlashCommandGroup

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from resources.shared import CONTEXTS, INTEGRATION_TYPES

from .config import LOG_COMPONENT
from .database import TimeoutDatabase

database = TimeoutDatabase()


class TimeoutCreateDeleteView(discord.ui.DesignerView):
	def __init__(self, timeout_id: str, created: bool):
		super().__init__(timeout=None)

		container = discord.ui.Container(colour=discord.Colour.green() if created else discord.Colour.red())
		super().add_item(container)

		title_text = discord.ui.TextDisplay(f"### {'Created' if created else 'Deleted'} timeout")
		container.add_item(title_text)

		body_text = discord.ui.TextDisplay(f"{'Created' if created else 'Deleted'} timeout `{timeout_id}`")
		container.add_item(body_text)


class TimeoutAddRemoveRoleView(discord.ui.DesignerView):
	def __init__(self, role_mention: str, timeout_id: str, added: bool):
		super().__init__(timeout=None)

		container = discord.ui.Container(colour=discord.Colour.green() if added else discord.Colour.red())
		super().add_item(container)

		title_text = discord.ui.TextDisplay(f"### {'Added' if added else 'Removed'} timeout role")
		container.add_item(title_text)

		body_text = discord.ui.TextDisplay(f"{'Added' if added else 'Removed'} role {role_mention} {'to' if added else 'from'} `{timeout_id}`")
		container.add_item(body_text)


class TimeoutAllowSelfAssignView(discord.ui.DesignerView):
	def __init__(self, timeout_id: str, allowed: bool):
		super().__init__(timeout=None)

		container = discord.ui.Container(colour=discord.Colour.green() if allowed else discord.Colour.red())
		super().add_item(container)

		title_text = discord.ui.TextDisplay(f"### {'Allowed' if allowed else 'Disallowed'} self assign of timeout")
		container.add_item(title_text)

		body_text = discord.ui.TextDisplay(f"{'Allowed' if allowed else 'Disallowed'} self assign of timeout `{timeout_id}`")
		container.add_item(body_text)


class TimeoutUserView(discord.ui.DesignerView):
	def __init__(self, timeout_id: str, user: discord.Member, end_date: datetime | None, reason: str | None):
		super().__init__(timeout=None)

		container = discord.ui.Container(colour=discord.Colour.red())
		super().add_item(container)

		title_text = discord.ui.TextDisplay("### Timed out user")
		container.add_item(title_text)

		body_text = discord.ui.TextDisplay(f"Timed out user {user.mention} with timeout `{timeout_id}`")
		container.add_item(body_text)

		if end_date is not None:
			date_string = discord.utils.format_dt(end_date, style='R')
			date_text = discord.ui.TextDisplay(f"Ends in {date_string}")
			container.add_item(date_text)

		reason_header = discord.ui.TextDisplay("### Reason")
		container.add_item(reason_header)

		reason_text = discord.ui.TextDisplay(reason if reason is not None else "No reason provided")
		container.add_item(reason_text)


class UntimeoutUserView(discord.ui.DesignerView):
	def __init__(self, timeout_id: str, user: discord.Member, reason: str | None):
		super().__init__(timeout=None)

		container = discord.ui.Container(colour=discord.Colour.green())
		super().add_item(container)

		title_text = discord.ui.TextDisplay("### Removed timeout from user")
		container.add_item(title_text)

		body_text = discord.ui.TextDisplay(f"Removed timeout from user {user.mention} with timeout `{timeout_id}`")
		container.add_item(body_text)

		reason_header = discord.ui.TextDisplay("### Reason")
		container.add_item(reason_header)

		reason_text = discord.ui.TextDisplay(reason if reason is not None else "No reason provided")
		container.add_item(reason_text)


class Timeout(commands.Cog):
	command_group = SlashCommandGroup("timeout", "Timeout functions", contexts=CONTEXTS, integration_types=INTEGRATION_TYPES)

	def __init__(self, bot: discord.Bot):
		self.bot = bot

		self.scheduler = AsyncIOScheduler()

	@commands.Cog.listener()
	async def on_ready(self):
		# Clear out all the expired timeouts
		for raw_timeout in database.get_expired_timeouts():
			guild_id, user_id, timeout_id = raw_timeout

			guild = await self.bot.get_or_fetch(discord.Guild, guild_id)
			member = await guild.get_or_fetch(discord.Member, user_id)

			await self.untimeout_user(guild_id, timeout_id, member)

		# Schedule all the active timeouts
		active_timeouts = database.get_timeouts()

		for guild_id, user_id, timeout_id, end_date in active_timeouts:
			if end_date is not None:
				exec_time = datetime.strptime(end_date, "%Y-%m-%d %H:%M:%S")

				guild = await self.bot.get_or_fetch(discord.Guild, guild_id)
				member = await guild.get_or_fetch(discord.Member, user_id)

				self.schedule_untimeout(guild_id, timeout_id, member, exec_time)

		self.scheduler.start()

	def schedule_untimeout(self, guild_id: int, timeout_id: str, member: discord.Member, end_date: datetime):
		job_id = f"{guild_id}-{member.id}-{timeout_id}"

		if not self.scheduler.get_job(job_id):
			self.scheduler.add_job(
				self.untimeout_user,
				"date",
				run_date=end_date,
				args=[guild_id, timeout_id, member],
				id=job_id,
			)

	hm_regex = re.compile(r"((?P<years>\d+)y)?((?P<months>\d+)M)?((?P<weeks>\d+)w)?((?P<days>\d+)d)?((?P<hours>\d+)h)?((?P<minutes>\d+)m)?((?P<seconds>\d+)s)?")

	def hm_to_date(self, hm_str: str):
		"""Converts an hour-minute string to a time in the future.

		This is mostly borrowed from Dozer."""

		matches = re.match(self.hm_regex, hm_str).groupdict()
		years = int(matches.get('years') or 0)
		months = int(matches.get('months') or 0)
		weeks = int(matches.get('weeks') or 0)
		days = int(matches.get('days') or 0)
		hours = int(matches.get('hours') or 0)
		minutes = int(matches.get('minutes') or 0)
		seconds = int(matches.get('seconds') or 0)
		val = int((years * 3.154e+7) + (months * 2.628e+6) + (weeks * 604800) + (days * 86400) + (hours * 3600) + (minutes * 60) + seconds)
		# Make sure it is a positive number, and it doesn't exceed the max 32-bit int
		seconds = max(0, min(2147483647, val))

		return datetime.now() + timedelta(seconds=seconds)

	@command_group.command(name="create_timeout", description="Creates a timeout category that you can assign roles and channels to.")
	@commands.has_permissions(administrator=True)
	async def create_timeout(self, ctx, timeout_id: str):
		try:
			database.insert_timeout_config(ctx.guild.id, timeout_id)

			await ctx.respond(view=TimeoutCreateDeleteView(timeout_id, True))
		except sqlite3.IntegrityError:
			await ctx.respond(f"Failed to create timeout: a timeout with name `{timeout_id}` already exists!")

	@command_group.command(name="delete_timeout", description="Deletes a timeout category. THIS CAN NOT BE UNDONE!")
	@commands.has_permissions(administrator=True)
	async def delete_timeout(self, ctx, timeout_id: str):
		try:
			# Remove existing timeouts
			for user_id in database.check_for_timeouts(ctx.guild.id, timeout_id):
				member = await ctx.guild.get_or_fetch(discord.Member, user_id[0])

				await self.untimeout_user(ctx.guild.id, timeout_id, member)

			database.remove_timeout_config(ctx.guild.id, timeout_id)

			await ctx.respond(view=TimeoutCreateDeleteView(timeout_id, False))
		except ValueError:
			await ctx.respond(f"Failed to delete timeout: no timeout exists with name `{timeout_id}`!")

	@command_group.command(name="add_role", description="Adds a role to the given timeout category, which will be assigned when the timeout is active.")
	@commands.has_permissions(administrator=True)
	async def add_role(self, ctx, timeout_id: str, role: discord.Role):
		try:
			database.add_timeout_role(ctx.guild.id, timeout_id, role.id)

			# Update existing timeouts
			for user_id in database.check_for_timeouts(ctx.guild.id, timeout_id):
				member = await ctx.guild.get_or_fetch(discord.Member, user_id[0])

				await member.add_roles(role)

			await ctx.respond(view=TimeoutAddRemoveRoleView(role.mention, timeout_id, True), allowed_mentions=discord.AllowedMentions(roles=False))
		except ValueError:
			await ctx.respond(f"Failed to add role: role {role.mention} already in timeout `{timeout_id}`", allowed_mentions=discord.AllowedMentions(roles=False))

	@command_group.command(name="remove_role", description="Removes a role from the given timeout category.")
	@commands.has_permissions(administrator=True)
	async def remove_role(self, ctx, timeout_id: str, role: discord.Role):
		try:
			database.remove_timeout_role(ctx.guild.id, timeout_id, role.id)

			# Update existing timeouts
			for user_id in database.check_for_timeouts(ctx.guild.id, timeout_id):
				member = await ctx.guild.get_or_fetch(discord.Member, user_id[0])

				await member.remove_roles(role)

			await ctx.respond(view=TimeoutAddRemoveRoleView(role.mention, timeout_id, False), allowed_mentions=discord.AllowedMentions(roles=False))
		except KeyError:
			await ctx.respond(f"Failed to remove role: role {role.mention} not in timeout `{timeout_id}`", allowed_mentions=discord.AllowedMentions(roles=False))

	@command_group.command(name="allow_self_assign", description="Sets whether or not the user should be allowed to self-assign this timeout.")
	@commands.has_permissions(administrator=True)
	async def allow_self_assign(self, ctx, timeout_id: str, allow: bool):
		database.set_timeout_self_assignable(ctx.guild.id, timeout_id, allow)

		await ctx.respond(view=TimeoutAllowSelfAssignView(timeout_id, allow))

	@command_group.command(name="timeout_user", description="Time out a user.")
	@commands.has_permissions(administrator=True)
	async def timeout_user_command(self, ctx, timeout_id: str, user: discord.Member, end_in: discord.Option(str, required=False), reason: discord.Option(str, required=False)):
		try:
			date = self.hm_to_date(end_in) if end_in is not None else None

			await self.timeout_user(ctx.guild.id, timeout_id, user, date, ctx.author.id, reason)

			await ctx.respond(view=TimeoutUserView(timeout_id, user, date, reason), allowed_mentions=discord.AllowedMentions(users=False))
		except sqlite3.IntegrityError:
			await ctx.respond(f"User {user.mention} already has timeout `{timeout_id}`. Untimeout them first before attempting to timeout them.", allowed_mentions=discord.AllowedMentions(users=False))

	@command_group.command(name="untimeout_user", description="Remove a time out from a user.")
	@commands.has_permissions(administrator=True)
	async def untimeout_user_command(self, ctx, timeout_id: str, user: discord.Member, reason: discord.Option(str, required=False)):
		await self.untimeout_user(ctx.guild.id, timeout_id, user)

		await ctx.respond(view=UntimeoutUserView(timeout_id, user, reason), allowed_mentions=discord.AllowedMentions(users=False))

	@command_group.command(name="selftimeout", description="Time out yourself.")
	async def selftimeoutcommand(self, ctx, timeout_id: str, end_in: str, reason: discord.Option(str, required=False)):
		if database.get_timeout_self_assignable(ctx.guild.id, timeout_id):
			try:
				date = self.hm_to_date(end_in) if end_in is not None else None

				await self.timeout_user(ctx.guild.id, timeout_id, ctx.author, date, ctx.author.id, reason)

				await ctx.respond(view=TimeoutUserView(timeout_id, ctx.author, date, reason), allowed_mentions=discord.AllowedMentions(users=False))
			except sqlite3.IntegrityError:
				await ctx.respond(f"You already has timeout `{timeout_id}`!")
		else:
			await ctx.respond(f"Not able to self assign timeout `{timeout_id}`!")

	async def timeout_user(self, guild_id: int, timeout_id: str, user: discord.Member, end_date: datetime | None, timeout_by: int, reason: str | None):
		database.add_timeout(guild_id, user.id, timeout_id, end_date, timeout_by, reason)

		roles = database.get_timeout_roles(guild_id, timeout_id)

		await user.add_roles(*map(discord.Object, roles))

		if end_date is not None:
			self.schedule_untimeout(guild_id, timeout_id, user, end_date)

	async def untimeout_user(self, guild_id: int, timeout_id: str, user: discord.Member):
		roles = database.get_timeout_roles(guild_id, timeout_id)

		await user.remove_roles(*map(discord.Object, roles))

		job_id = f"{guild_id}-{user.id}-{timeout_id}"

		if self.scheduler.get_job(job_id):
			self.scheduler.remove_job(job_id)

		database.remove_timeout(guild_id, user.id, timeout_id)


def setup(bot):
	bot.add_cog(Timeout(bot))


def teardown(bot):
	bot.remove_cog("Timeout")
