from .engagement import Engagement

async def setup(bot):
    await bot.add_cog(Engagement(bot))
