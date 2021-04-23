require 'html-proofer'

options = { 
    :url_ignore => [/localhost:4000/,/geoinquiets.github.io/],
    :log_level => :info,
    :assume_extension => true ,
    :external_only => true,
    :check_sri => false,
    :check_html => false,
    :check_img_http => true,
    :check_opengraph => false,
    :enforce_https => false,
    :cache => {
      :timeframe => '1w'
    },
    :typhoeus => { 
        :followlocation => true,
        :ssl_verifypeer => false,
        :ssl_verifyhost => 0,
        :connecttimeout => 30,
        :timeout => 30
    }
}
HTMLProofer.check_directory(File.join(File.dirname(__FILE__), '../_site'), options).run