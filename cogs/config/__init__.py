from .config import Config

async def setup(bot):
    await bot.add_cog(Config(bot))