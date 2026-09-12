from .automation import Automation

async def setup(bot):
    await bot.add_cog(Automation(bot))