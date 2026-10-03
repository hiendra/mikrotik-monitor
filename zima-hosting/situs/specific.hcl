# Specific config for the ClusterNet landing page (this folder).
#
# The deploy context is the folder containing this file, so only index.html,
# server.mjs and these config files are uploaded — never the parent folder's
# .env / secrets.

build "web" {
  base = "node"
}

service "web" {
  build   = build.web
  command = "node server.mjs"

  endpoint {
    public = true

    health_check {
      path = "/"
    }
  }

  env = {
    PORT = port
  }
}
