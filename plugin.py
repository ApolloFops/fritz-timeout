import discord
from discord.ext import commands
from discord.commands import SlashCommandGroup

from resources.shared import CONTEXTS, INTEGRATION_TYPES

from .config import LOG_COMPONENT
from .database import TimeoutDatabase

database = TimeoutDatabase()


class Timeout(commands.Cog):
	command_group = SlashCommandGroup("timeout", "Timeout functions", contexts=CONTEXTS, integration_types=INTEGRATION_TYPES)

	def __init__(self, bot: discord.Bot):
		self.bot = bot

	@command_group.command(name="create_timeout", description="Creates a timeout category that you can assign roles and channels to.")
	@commands.has_permissions(administrator=True)
	async def create_timeout(self, ctx, timeout_id: str):
		database.insert_timeout_config(ctx.guild.id, timeout_id)

		await ctx.respond(f"Created timeout `{timeout_id}`")

	@command_group.command(name="remove_timeout", description="Removes a timeout category.")
	@commands.has_permissions(administrator=True)
	async def remove_timeout(self, ctx, timeout_id: str):
		database.remove_timeout_config(ctx.guild.id, timeout_id)

		await ctx.respond(f"Removed timeout `{timeout_id}`")

	@command_group.command(name="add_role", description="Adds a role to the given timeout category, which will be assigned when the timeout is active.")
	@commands.has_permissions(administrator=True)
	async def add_role(self, ctx, timeout_id: str, role: discord.Role):
		database.add_timeout_role(ctx.guild.id, timeout_id, role.id)

		await ctx.respond(f"Added role {role.mention} to timeout `{timeout_id}`", allowed_mentions=discord.AllowedMentions(roles=False))

		await ctx.send(str(database.get_timeout_roles(ctx.guild.id, timeout_id)))

	@command_group.command(name="remove_role", description="Removes a role from the given timeout category.")
	@commands.has_permissions(administrator=True)
	async def remove_role(self, ctx, timeout_id: str, role: discord.Role):
		database.remove_timeout_role(ctx.guild.id, timeout_id, role.id)

		await ctx.respond(f"Removed role {role.mention} from timeout `{timeout_id}`", allowed_mentions=discord.AllowedMentions(roles=False))

		await ctx.send(str(database.get_timeout_roles(ctx.guild.id, timeout_id)))


def setup(bot):
	bot.add_cog(Timeout(bot))


def teardown(bot):
	bot.remove_cog("Timeout")
