package com.redpiano.mixin;

import com.redpiano.RedPiano;
import com.redpiano.RedPianoMap;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Holder;
import net.minecraft.core.particles.ParticleTypes;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.sounds.SoundEvent;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.NoteBlock;
import net.minecraft.world.level.block.state.BlockState;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

/**
 * 让真·音符盒(minecraft:note_block)发声时, 若其正下方方块在映射表中,
 * 改播我们的自定义钢琴音效 + 按 note 档移调 + 自定义音量, 并喷 NOTE 粒子。
 * 否则原样走原版 16 乐器。100% 真音符盒, 只把"垫底->音色"表解锁。
 */
@Mixin(NoteBlock.class)
public class NoteBlockMixin {
    @Inject(method = "triggerEvent", at = @At("HEAD"), cancellable = true)
    private void redpiano$customSound(BlockState state, Level level, BlockPos pos, int id, int param,
                                      CallbackInfoReturnable<Boolean> cir) {
        RedPianoMap.Entry e = RedPianoMap.lookup(level.getBlockState(pos.below()).getBlock());
        if (e == null) return;                                   // 非映射方块 -> 原版
        int note = state.getValue(NoteBlock.NOTE);
        float pitch = NoteBlock.getPitchFromNote(note);          // 强制移调(原版自定义音效不移调)
        level.addParticle(ParticleTypes.NOTE, pos.getX() + 0.5, pos.getY() + 1.2, pos.getZ() + 0.5,
                note / 24.0, 0.0, 0.0);                          // 真音符盒粒子
        Holder<SoundEvent> holder = Holder.direct(SoundEvent.createVariableRangeEvent(ResourceLocation.parse(e.sound)));
        // 服务端排队, 由 RedPiano 在【游戏刻末】统一发声(以玩家为中心=与距离无关永不断音; 整刻 N 算复音增益; 微抖)。
        // 真音符盒视觉(粒子/方块/机制)不变; 仅"声音投递"改为以玩家为中心(老命令方块版 @s ~ ~ ~ 同思路)。
        if (level instanceof ServerLevel) {
            long seed = pos.asLong() * 31L + level.getGameTime();    // (位置,时刻)确定性种子 -> 去"逐比特复印感"
            RedPiano.QUEUE.add(new RedPiano.Pending(holder, e.volume, pitch, seed));
        }
        cir.setReturnValue(true);                                // 取消原版, 事件已处理
    }
}
