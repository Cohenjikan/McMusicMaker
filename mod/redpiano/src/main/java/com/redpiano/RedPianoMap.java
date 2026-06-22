package com.redpiano;

import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.Blocks;

import java.util.HashMap;
import java.util.Map;

/** 「垫底方块 -> (音效事件, 音量)」完整映射 (gen_redpiano_map.py 生成; 勿手改)。
 *  20 段 x 3 力度 = 60 条。原版只有 16 条且写死; 这里任意大。 */
public final class RedPianoMap {
    public static final class Entry {
        public final String sound;
        public final float volume;
        public Entry(String sound, float volume) { this.sound = sound; this.volume = volume; }
    }

    private static final Map<Block, Entry> MAP = new HashMap<>();
    static {
        MAP.put(Blocks.WHITE_CONCRETE, new Entry("qzpno:pno_c1_p", 1.4f));
        MAP.put(Blocks.ORANGE_CONCRETE, new Entry("qzpno:pno_c1_mf", 1.7f));
        MAP.put(Blocks.MAGENTA_CONCRETE, new Entry("qzpno:pno_c1_f", 2.0f));
        MAP.put(Blocks.LIGHT_BLUE_CONCRETE, new Entry("qzpno:pno_ds1_p", 1.4f));
        MAP.put(Blocks.YELLOW_CONCRETE, new Entry("qzpno:pno_ds1_mf", 1.7f));
        MAP.put(Blocks.LIME_CONCRETE, new Entry("qzpno:pno_ds1_f", 2.0f));
        MAP.put(Blocks.PINK_CONCRETE, new Entry("qzpno:pno_fs1_p", 1.4f));
        MAP.put(Blocks.GRAY_CONCRETE, new Entry("qzpno:pno_fs1_mf", 1.7f));
        MAP.put(Blocks.LIGHT_GRAY_CONCRETE, new Entry("qzpno:pno_fs1_f", 2.0f));
        MAP.put(Blocks.CYAN_CONCRETE, new Entry("qzpno:pno_a1_p", 1.4f));
        MAP.put(Blocks.PURPLE_CONCRETE, new Entry("qzpno:pno_a1_mf", 1.7f));
        MAP.put(Blocks.BLUE_CONCRETE, new Entry("qzpno:pno_a1_f", 2.0f));
        MAP.put(Blocks.BROWN_CONCRETE, new Entry("qzpno:pno_c2_p", 1.4f));
        MAP.put(Blocks.GREEN_CONCRETE, new Entry("qzpno:pno_c2_mf", 1.7f));
        MAP.put(Blocks.RED_CONCRETE, new Entry("qzpno:pno_c2_f", 2.0f));
        MAP.put(Blocks.BLACK_CONCRETE, new Entry("qzpno:pno_ds2_p", 1.4f));
        MAP.put(Blocks.WHITE_TERRACOTTA, new Entry("qzpno:pno_ds2_mf", 1.7f));
        MAP.put(Blocks.ORANGE_TERRACOTTA, new Entry("qzpno:pno_ds2_f", 2.0f));
        MAP.put(Blocks.MAGENTA_TERRACOTTA, new Entry("qzpno:pno_fs2_p", 1.4f));
        MAP.put(Blocks.LIGHT_BLUE_TERRACOTTA, new Entry("qzpno:pno_fs2_mf", 1.7f));
        MAP.put(Blocks.YELLOW_TERRACOTTA, new Entry("qzpno:pno_fs2_f", 2.0f));
        MAP.put(Blocks.LIME_TERRACOTTA, new Entry("qzpno:pno_a2_p", 1.4f));
        MAP.put(Blocks.PINK_TERRACOTTA, new Entry("qzpno:pno_a2_mf", 1.7f));
        MAP.put(Blocks.GRAY_TERRACOTTA, new Entry("qzpno:pno_a2_f", 2.0f));
        MAP.put(Blocks.LIGHT_GRAY_TERRACOTTA, new Entry("qzpno:pno_c3_p", 1.4f));
        MAP.put(Blocks.CYAN_TERRACOTTA, new Entry("qzpno:pno_c3_mf", 1.7f));
        MAP.put(Blocks.PURPLE_TERRACOTTA, new Entry("qzpno:pno_c3_f", 2.0f));
        MAP.put(Blocks.BLUE_TERRACOTTA, new Entry("qzpno:pno_ds3_p", 1.4f));
        MAP.put(Blocks.BROWN_TERRACOTTA, new Entry("qzpno:pno_ds3_mf", 1.7f));
        MAP.put(Blocks.GREEN_TERRACOTTA, new Entry("qzpno:pno_ds3_f", 2.0f));
        MAP.put(Blocks.RED_TERRACOTTA, new Entry("qzpno:pno_fs3_p", 1.4f));
        MAP.put(Blocks.BLACK_TERRACOTTA, new Entry("qzpno:pno_fs3_mf", 1.7f));
        MAP.put(Blocks.WHITE_WOOL, new Entry("qzpno:pno_fs3_f", 2.0f));
        MAP.put(Blocks.ORANGE_WOOL, new Entry("qzpno:pno_a3_p", 1.4f));
        MAP.put(Blocks.MAGENTA_WOOL, new Entry("qzpno:pno_a3_mf", 1.7f));
        MAP.put(Blocks.LIGHT_BLUE_WOOL, new Entry("qzpno:pno_a3_f", 2.0f));
        MAP.put(Blocks.YELLOW_WOOL, new Entry("qzpno:pno_c4_p", 1.4f));
        MAP.put(Blocks.LIME_WOOL, new Entry("qzpno:pno_c4_mf", 1.7f));
        MAP.put(Blocks.PINK_WOOL, new Entry("qzpno:pno_c4_f", 2.0f));
        MAP.put(Blocks.GRAY_WOOL, new Entry("qzpno:pno_ds4_p", 1.4f));
        MAP.put(Blocks.LIGHT_GRAY_WOOL, new Entry("qzpno:pno_ds4_mf", 1.7f));
        MAP.put(Blocks.CYAN_WOOL, new Entry("qzpno:pno_ds4_f", 2.0f));
        MAP.put(Blocks.PURPLE_WOOL, new Entry("qzpno:pno_fs4_p", 1.4f));
        MAP.put(Blocks.BLUE_WOOL, new Entry("qzpno:pno_fs4_mf", 1.7f));
        MAP.put(Blocks.BROWN_WOOL, new Entry("qzpno:pno_fs4_f", 2.0f));
        MAP.put(Blocks.GREEN_WOOL, new Entry("qzpno:pno_a4_p", 1.4f));
        MAP.put(Blocks.RED_WOOL, new Entry("qzpno:pno_a4_mf", 1.7f));
        MAP.put(Blocks.BLACK_WOOL, new Entry("qzpno:pno_a4_f", 2.0f));
        MAP.put(Blocks.STONE, new Entry("qzpno:pno_c5_p", 1.4f));
        MAP.put(Blocks.GRANITE, new Entry("qzpno:pno_c5_mf", 1.7f));
        MAP.put(Blocks.DIORITE, new Entry("qzpno:pno_c5_f", 2.0f));
        MAP.put(Blocks.ANDESITE, new Entry("qzpno:pno_ds5_p", 1.4f));
        MAP.put(Blocks.DEEPSLATE, new Entry("qzpno:pno_ds5_mf", 1.7f));
        MAP.put(Blocks.CALCITE, new Entry("qzpno:pno_ds5_f", 2.0f));
        MAP.put(Blocks.TUFF, new Entry("qzpno:pno_fs5_p", 1.4f));
        MAP.put(Blocks.QUARTZ_BLOCK, new Entry("qzpno:pno_fs5_mf", 1.7f));
        MAP.put(Blocks.SMOOTH_STONE, new Entry("qzpno:pno_fs5_f", 2.0f));
        MAP.put(Blocks.SANDSTONE, new Entry("qzpno:pno_a5_p", 1.4f));
        MAP.put(Blocks.RED_SANDSTONE, new Entry("qzpno:pno_a5_mf", 1.7f));
        MAP.put(Blocks.BRICKS, new Entry("qzpno:pno_a5_f", 2.0f));
    }

    public static Entry lookup(Block b) { return MAP.get(b); }

    private RedPianoMap() {}
}
