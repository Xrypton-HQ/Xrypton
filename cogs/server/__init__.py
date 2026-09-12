from .server import Server

async def setup(bot):
    await bot.add_cog(Server(bot))