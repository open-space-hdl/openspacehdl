# Composer fixtures

Test data from the website repository open-space-hdl/open-space-hdl.github.io at commit 8fa23f0 (Composer
generator 0.9.9-beta, catalog 75d78f7588f4):

- `schema/system-1.json`, `schema/system-2.json`: the published schemas of the Composer file format
  (`composer/schema/`).
- `spw_rmap_node/spw_rmap_node.composer.json`, `spacefibre_node/spacefibre_node.composer.json`,
  `encrypted_spp_over_spw/encrypted_spp_over_spw.composer.json` and
  `compressed_images_over_spw/compressed_images_over_spw.composer.json`: the Composer examples of these names
  (`assets/composer/examples/`), and in `<example>/hdl/` the export of each, written by
  `node tools/composer_hdl.mjs` of the same commit.

From commit c226963 (Composer generator 0.10.0-beta, catalog ceeeddaa62ed), for `formatVersion` 3 (reset groups):

- `schema/system-3.json`;
- `spw_compression_node_pipeline_reset/spw_compression_node_pipeline_reset.composer.json` and its export in
  `spw_compression_node_pipeline_reset/hdl/`, written by `node tools/composer_hdl.mjs` of that commit.

They are licensed as the website repository states (MIT for code, CC BY 4.0 for content).
