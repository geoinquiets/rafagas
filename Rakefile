require "rubygems"
require 'rake'
require 'yaml'
require 'time'

SOURCE = "."
CONFIG = {
  'version' => "0.2.13",
  'themes' => File.join(SOURCE, "_includes", "themes"),
  'layouts' => File.join(SOURCE, "_layouts"),
  'posts' => File.join(SOURCE, "_posts"),
  'pages' => File.join(SOURCE, "_pages"),
  'post_ext' => "md",
}

desc "Launch preview environment"
task :preview do
  system "JEKYLL_ENV=development bundle exec jekyll serve --incremental --config _config.yml"
end # task :preview

desc "Build site"
task :build do
  system "JEKYLL_ENV=production bundle exec jekyll build"
end # task :build

desc "Clean the stuff"
task :clean do
  system "rm -rf _site"
end # task :clean

# Internal: Process theme package manifest file.
#
# theme_path - String, Required. File path to theme package.
#
# Returns theme manifest hash
def verify_manifest(theme_path)
  manifest_path = File.join(theme_path, "manifest.yml")
  manifest_file = File.open( manifest_path )
  abort("rake aborted: repo must contain valid manifest.yml") unless File.exist? manifest_file
  manifest = YAML.load( manifest_file )
  manifest_file.close
  manifest
end

def ask(message, valid_options)
  if valid_options
    answer = get_stdin("#{message} #{valid_options.to_s.gsub(/"/, '').gsub(/, /,'/')} ") while !valid_options.include?(answer)
  else
    answer = get_stdin(message)
  end
  answer
end

def get_stdin(message)
  print message
  STDIN.gets.chomp
end

#Load custom rake scripts
Dir['_rake/*.rake'].each { |r| load r }
