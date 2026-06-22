package com.redpiano;

import net.fabricmc.api.ModInitializer;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerTickEvents;
import net.minecraft.core.Holder;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.sounds.SoundEvent;
import net.minecraft.sounds.SoundSource;
import net.minecraft.world.scores.Objective;
import net.minecraft.world.scores.ReadOnlyScoreInfo;
import net.minecraft.world.scores.ScoreHolder;
import net.minecraft.world.scores.Scoreboard;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.ArrayList;
import java.util.List;
import java.util.Random;

/**
 * 真音符盒发声(以玩家为中心, 与距离无关), 并在【游戏刻末】统一发声:
 *  - 复音增益: 本刻 N 个音 -> 音量 ×1/sqrt(N)(等功率混音, 防和弦叠加削顶)。
 *  - 微抖动: 每次触发按 (位置,时刻) 确定性种子做 ±3 音分音高 / ±2% 音量微抖, 去"逐比特复印感"。
 * 两者均可被命令方块经记分板 `rpcfg` 开关(假人 poly / human, 非 0=开; 缺省=都开)。
 */
public class RedPiano implements ModInitializer {
    public static final Logger LOG = LoggerFactory.getLogger("redpiano");

    /** 本游戏刻待发声的音符(NoteBlockMixin 服务端排队, 刻末统一发, 以便按整刻 N 算复音增益)。 */
    public record Pending(Holder<SoundEvent> sound, float volume, float pitch, long seed) {}
    public static final List<Pending> QUEUE = new ArrayList<>();

    @Override
    public void onInitialize() {
        ServerTickEvents.END_SERVER_TICK.register(this::flush);
        LOG.info("[RedPiano] loaded — real note blocks -> per-player centered sound + polyphony-gain + humanize.");
    }

    private void flush(MinecraftServer server) {
        if (QUEUE.isEmpty()) return;
        int n = QUEUE.size();
        int poly = readCfg(server, "poly", 1);      // 命令方块开关: 0=关复音增益; 非0/缺省=开
        boolean human = readCfg(server, "human", 1) != 0;
        float polyGain = (poly != 0 && n > 1) ? (float) (1.0 / Math.sqrt(n)) : 1.0f;
        List<ServerPlayer> players = server.getPlayerList().getPlayers();
        for (Pending q : QUEUE) {
            float vol = q.volume() * polyGain;
            float pitch = q.pitch();
            if (human) {
                Random r = new Random(q.seed());
                pitch *= (float) Math.pow(2.0, (r.nextDouble() * 2 - 1) * 3.0 / 1200.0);   // ±3 音分(<JND, 仅去相关)
                vol   *= (float) (1.0 + (r.nextDouble() * 2 - 1) * 0.02);                  // ±2% 音量抖
            }
            for (ServerPlayer p : players) {
                p.level().playSeededSound(null, p.getX(), p.getY(), p.getZ(),
                        q.sound(), SoundSource.RECORDS, vol, pitch, 0L);
            }
        }
        QUEUE.clear();
    }

    /** 读 rpcfg 记分板某假人分数; 无目标/无分则返回 def(=默认开)。 */
    private static int readCfg(MinecraftServer server, String holder, int def) {
        Scoreboard sb = server.getScoreboard();
        Objective obj = sb.getObjective("rpcfg");
        if (obj == null) return def;
        ReadOnlyScoreInfo info = sb.getPlayerScoreInfo(ScoreHolder.forNameOnly(holder), obj);
        return info == null ? def : info.value();
    }
}
