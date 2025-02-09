// Entry point for Webpack
// Dynamically require all JavaScript files in the js folder
const jsContext = require.context("./js", true, /\.js$/);
jsContext.keys().forEach(jsContext);

// Dynamically require all CSS files in the styles folder
const cssContext = require.context("./styles", true, /\.css$/);
cssContext.keys().forEach(cssContext);
