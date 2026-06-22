package com.redpiano.mixin;

import com.redpiano.RedPianoMap;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Holder;
import net.minecraft.core.particles.ParticleTypes;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.sounds.SoundEvent;
import net.minecraft.sounds.SoundSource;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
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
        // 不再在音符盒位置播"定位音"(玩家飞远=出声音球半径 -> 客户端每刻重算音量, 出界即剪断采样=断音)。
        // 改为: 服务端给【每个玩家在其自身脚下】播放该音 -> 听者永远在声音球中心 -> 与距离无关, 永不被剪断。
        // 真音符盒视觉(粒子/方块/机制)不变; 仅把"声音投递"从定位改为以玩家为中心(老命令方块版 @s ~ ~ ~ 同思路)。
        if (level instanceof ServerLevel server) {
            for (ServerPlayer p : server.players()) {
                server.playSeededSound(null, p.getX(), p.getY(), p.getZ(),
                        holder, SoundSource.RECORDS, e.volume, pitch, 0L);
            }
        }
        cir.setReturnValue(true);                                // 取消原版, 事件已处理
    }
}
