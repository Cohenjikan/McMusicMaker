package com.redpiano;

import net.fabricmc.api.ModInitializer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class RedPiano implements ModInitializer {
    public static final Logger LOG = LoggerFactory.getLogger("redpiano");

    @Override
    public void onInitialize() {
        LOG.info("[RedPiano] loaded — real note blocks on mapped blocks play custom sounds (no fake block).");
    }
}
