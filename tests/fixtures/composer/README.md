# Composer fixtures

Test data from the website repository open-space-hdl/open-space-hdl.github.io at commit 95282c0:

- `schema/system-1.json`, `schema/system-2.json`: the published schemas of the Composer file format
  (`composer/schema/`).
- `spw_rmap_node/spw_rmap_node.composer.json`, `spacefibre_node/spacefibre_node.composer.json`,
  `encrypted_spp_over_spw/encrypted_spp_over_spw.composer.json` and
  `compressed_images_over_spw/compressed_images_over_spw.composer.json`: the Composer examples of these names
  (`assets/composer/examples/`), and in `<example>/hdl/` the export of each, written by
  `node tools/composer_hdl.mjs` of the same commit.

They are licensed as the website repository states (MIT for code, CC BY 4.0 for content).
